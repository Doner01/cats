const {PGlite} = require('@electric-sql/pglite');
const {uuid_ossp} = require('@electric-sql/pglite/contrib/uuid_ossp');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
(async()=>{
 const db=new PGlite({extensions:{uuid_ossp}});
 await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS; CREATE SCHEMA auth; CREATE SCHEMA storage;
 CREATE TABLE auth.users(id uuid primary key, email text, raw_user_meta_data jsonb default '{}'::jsonb);
 CREATE TABLE storage.buckets(id text primary key, name text, public boolean);
 CREATE TABLE storage.objects(id uuid primary key, bucket_id text);`);
 const schema=fs.readFileSync(path.join(__dirname,'../supabase_migration.sql'),'utf8').replace('CREATE EXTENSION IF NOT EXISTS "pgcrypto";','');
 await db.exec(schema); await db.exec(schema);
 for(const name of ['20260902_favorites.sql','20260902_roadmap.sql','20260902_phone_comments.sql']) {
  const migration=fs.readFileSync(path.join(__dirname,'../migrations',name),'utf8');
  await db.exec(migration); await db.exec(migration);
 }
 const user='11111111-1111-4111-8111-111111111111';const other='22222222-2222-4222-8222-222222222222';const cat='33333333-3333-4333-8333-333333333333';
 await db.query(`INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES($1,'cat@example.com','{"display_name":"Original"}'),($2,'other@example.com','{}')`,[user,other]);
 assert.equal((await db.query('SELECT count(*)::integer n FROM profiles')).rows[0].n,2);
 await db.query('INSERT INTO cats(id,user_id,name,image_url) VALUES($1,$2,\'Mochi\',\'https://example.com/cat.webp\')',[cat,user]);
 for(const [u,action,count] of [[user,'liked',1],[other,'liked',2],[user,'unliked',1]]){
 const r=await db.query('SELECT * FROM toggle_cat_like($1,$2)',[cat,u]);assert.deepEqual(r.rows[0],{action,likes_count:count});
 }
 await db.query('INSERT INTO comments(cat_id,user_id,comment) VALUES($1,$2,\'hello\')',[cat,user]);
 await db.query('UPDATE profiles SET display_name=\'Renamed\', avatar_url=\'https://example.com/new.webp\' WHERE id=$1',[user]);
 assert.equal((await db.query('SELECT user_name FROM cats')).rows[0].user_name,'Renamed');
 assert.equal((await db.query('SELECT user_name FROM comments')).rows[0].user_name,'Renamed');
 await db.query('UPDATE auth.users SET email=\'confirmed@example.com\' WHERE id=$1',[user]);
 assert.equal((await db.query('SELECT email FROM profiles WHERE id=$1',[user])).rows[0].email,'confirmed@example.com');
 await db.query('DELETE FROM auth.users WHERE id=$1',[other]);assert.equal((await db.query('SELECT likes_count FROM cats')).rows[0].likes_count,0);
 await db.query('DELETE FROM auth.users WHERE id=$1',[user]);
 for(const table of ['cats','likes','comments','profiles'])assert.equal((await db.query('SELECT count(*)::integer n FROM '+table)).rows[0].n,0);
 const googleUser='66666666-6666-4666-8666-666666666666';
 await db.query(`INSERT INTO auth.users(id,email,raw_user_meta_data) VALUES($1,'google@example.com','{"full_name":"Google Cat","role":"admin"}')`,[googleUser]);
 const profile=(await db.query('SELECT display_name,role FROM profiles WHERE id=$1',[googleUser])).rows[0];
 assert.deepEqual(profile,{display_name:'Google Cat',role:'user'});
 await db.query("INSERT INTO cats(id,user_id,name,image_url) VALUES($1,$2,'Cat','https://example.com/cat.webp')",[cat,googleUser]);
 const secondCat='77777777-7777-4777-8777-777777777777';
 await db.query("INSERT INTO cats(id,user_id,name,image_url) VALUES($1,$2,'Other','https://example.com/cat.webp')",[secondCat,googleUser]);
 const comment='88888888-8888-4888-8888-888888888888';
 const reply='99999999-9999-4999-8999-999999999999';
 await db.query("INSERT INTO comments(id,cat_id,user_id,comment) VALUES($1,$2,$3,'Root')",[comment,cat,googleUser]);
 await assert.rejects(db.query("INSERT INTO comments(cat_id,user_id,comment,parent_id) VALUES($1,$2,'Invalid',$3)",[secondCat,googleUser,comment]), /same cat/);
 await db.query("INSERT INTO comments(id,cat_id,user_id,comment,parent_id,reply_to_id) VALUES($1,$2,$3,'Reply',$4,$4)",[reply,cat,googleUser,comment]);
 await db.query("INSERT INTO notifications(user_id,cat_id,comment_id,message) VALUES($1,$2,$3,'Reply')",[googleUser,cat,reply]);
 await db.query('DELETE FROM comments WHERE id=$1',[comment]);
 assert.equal((await db.query('SELECT count(*)::integer n FROM notifications')).rows[0].n,0);
 assert.equal((await db.query('SELECT count(*)::integer n FROM comments')).rows[0].n,0);
 const phoneUser='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
 await db.query('INSERT INTO auth.users(id,email) VALUES($1,NULL)',[phoneUser]);
 assert.deepEqual((await db.query('SELECT display_name,email,phone,role FROM profiles WHERE id=$1',[phoneUser])).rows[0],{display_name:'Cat Lover',email:null,phone:null,role:'user'});
 await db.query("INSERT INTO comments(id,cat_id,user_id,comment) VALUES($1,$2,$3,'A comment')",[comment,cat,googleUser]);
 for(const [liked,count] of [[true,1],[true,1],[false,0],[false,0],[true,1]]) {
  assert.deepEqual((await db.query('SELECT * FROM set_comment_like($1,$2,$3)',[comment,phoneUser,liked])).rows[0],{liked,likes_count:count,cat_id:cat});
 }
 assert.equal((await db.query('SELECT updated_at FROM comments WHERE id=$1',[comment])).rows[0].updated_at,null);
 assert.equal((await db.query("SELECT status FROM edit_comment_with_window($1,$2,'Spoof',false)",[comment,phoneUser])).rows[0].status,'forbidden');
 await db.query("UPDATE comments SET created_at=clock_timestamp()-interval '119 seconds' WHERE id=$1",[comment]);
 assert.equal((await db.query("SELECT status FROM edit_comment_with_window($1,$2,'  Edited  ',false)",[comment,googleUser])).rows[0].status,'updated');
 assert.equal((await db.query('SELECT comment FROM comments WHERE id=$1',[comment])).rows[0].comment,'Edited');
 await db.query("UPDATE comments SET created_at=clock_timestamp()-interval '120 seconds' WHERE id=$1",[comment]);
 assert.equal((await db.query("SELECT status FROM edit_comment_with_window($1,$2,'Too late',false)",[comment,googleUser])).rows[0].status,'expired');
 assert.equal((await db.query('SELECT comment FROM comments WHERE id=$1',[comment])).rows[0].comment,'Edited');
 assert.equal((await db.query("SELECT status FROM edit_comment_with_window($1,$2,'Moderated',true)",[comment,phoneUser])).rows[0].status,'updated');
 await assert.rejects(db.query("SELECT * FROM edit_comment_with_window($1,$2,' ',true)",[comment,googleUser]),/Invalid comment length/);
 await db.query('DELETE FROM auth.users WHERE id=$1',[phoneUser]);
 assert.equal((await db.query('SELECT likes_count FROM comments WHERE id=$1',[comment])).rows[0].likes_count,0);
 await db.query('SELECT * FROM set_comment_like($1,$2,true)',[comment,googleUser]);
 await db.query('DELETE FROM comments WHERE id=$1',[comment]);
 assert.equal((await db.query('SELECT count(*)::integer n FROM comment_likes')).rows[0].n,0);
 for(const table of ['profiles','cats','comments','likes','comment_likes','notifications','favorites']) {
  assert.equal((await db.query("SELECT has_table_privilege('anon',$1,'SELECT') allowed",[table])).rows[0].allowed,false);
  assert.equal((await db.query("SELECT has_table_privilege('authenticated',$1,'INSERT') allowed",[table])).rows[0].allowed,false);
 }
 for(const fn of ['public.toggle_cat_like(uuid,uuid)','public.set_comment_like(uuid,uuid,boolean)','public.edit_comment_with_window(uuid,uuid,text,boolean)']) {
  for(const role of ['anon','authenticated','service_role']) {
   assert.equal((await db.query("SELECT has_function_privilege($1,$2,'execute') allowed",[role,fn])).rows[0].allowed,role==='service_role');
  }
 }
 console.log('Database checks passed: repeatable migrations, OAuth/phone profiles, roles, replies, cascades, idempotent comment likes, two-minute edits, voting, email sync, attribution and RPC permissions.');await db.close();
})().catch(e=>{console.error(e.message);process.exit(1)});

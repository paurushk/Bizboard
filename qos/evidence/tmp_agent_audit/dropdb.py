import psycopg
c = psycopg.connect("postgresql://bizboard:bizboard@127.0.0.1:5433/postgres", autocommit=True)
cur = c.cursor()
cur.execute("select pid, state, left(query,60) from pg_stat_activity where datname='test_bb_t1'")
print(cur.fetchall())
cur.execute("select pg_terminate_backend(pid) from pg_stat_activity where datname='test_bb_t1' and pid<>pg_backend_pid()")
cur.execute("set statement_timeout=0")
cur.execute("drop database if exists test_bb_t1")
print("dropped")

// 1. Graph size by node label.
MATCH (n) RETURN labels(n)[0] AS label, count(n) AS nodes ORDER BY nodes DESC;

// 2. Relationship counts by type, excluding hidden edges.
MATCH (:Person)-[r]->() WHERE r.hidden=false RETURN type(r) AS relationship, count(r) AS edges ORDER BY edges DESC;

// 3. School overlap with the public minimum of three.
MATCH (p:Person)-[r:STUDIED_AT]->(s:School)
WHERE r.hidden=false
WITH s, count(DISTINCT p) AS n WHERE n >= 3
RETURN s.name AS school, n ORDER BY n ASC LIMIT 10;

// 4. Company overlap with the public minimum of three.
MATCH (p:Person)-[r:WORKED_AT]->(c:Company)
WHERE r.hidden=false
WITH c, count(DISTINCT p) AS n WHERE n >= 3
RETURN c.name AS company, n ORDER BY n ASC LIMIT 10;

// 5. Rare school-to-company path; use aggregate counts in a public demo.
MATCH (s:School)<-[a:STUDIED_AT]-(p:Person)-[b:WORKED_AT]->(c:Company)
WHERE a.hidden=false AND b.hidden=false
WITH s, c, count(DISTINCT p) AS n WHERE n >= 3 AND n <= 12
RETURN s.name AS school, c.name AS company, n ORDER BY n ASC LIMIT 10;

// 6. People who worked at two companies, counted once per pair.
MATCH (a:Company)<-[r1:WORKED_AT]-(p:Person)-[r2:WORKED_AT]->(b:Company)
WHERE a.id < b.id AND r1.hidden=false AND r2.hidden=false
WITH a, b, count(DISTINCT p) AS n WHERE n >= 3 AND n <= 12
RETURN a.name AS company_a, b.name AS company_b, n ORDER BY n ASC LIMIT 10;

// 7. Opt-in aggregate, without names.
MATCH (p:Person) RETURN count(p) AS guests, sum(CASE WHEN p.opted_in THEN 1 ELSE 0 END) AS opted_in;

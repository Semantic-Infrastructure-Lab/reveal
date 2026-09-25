CREATE TABLE users (
  id INT PRIMARY KEY,
  name TEXT
);

CREATE TABLE public.orders (
  id INT PRIMARY KEY,
  user_id INT
);

CREATE VIEW active_users AS SELECT * FROM users;

CREATE FUNCTION add_one(x INT) RETURNS INT AS $$
BEGIN
  RETURN x + 1;
END;
$$ LANGUAGE plpgsql;

CREATE INDEX idx_orders_user ON public.orders (user_id);

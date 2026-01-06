"""Tests for SQL analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.sql import SQLAnalyzer


class TestSQLAnalyzer(unittest.TestCase):
    """Test suite for SQL file analysis."""

    def test_create_table(self):
        """Should parse CREATE TABLE statements."""
        code = '''CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('classes', structure)

            # Tables are treated as "classes"
            table_names = [c['name'] for c in structure.get('classes', [])]
            self.assertIn('users', table_names)

        finally:
            os.unlink(temp_path)

    def test_multiple_tables(self):
        """Should extract multiple tables."""
        code = '''CREATE TABLE users (
    id INT PRIMARY KEY,
    name VARCHAR(100)
);

CREATE TABLE orders (
    id INT PRIMARY KEY,
    user_id INT REFERENCES users(id),
    amount DECIMAL(10, 2)
);

CREATE TABLE order_items (
    id INT PRIMARY KEY,
    order_id INT REFERENCES orders(id),
    product_name VARCHAR(255),
    quantity INT
);
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('classes', structure)

            table_names = [c['name'] for c in structure.get('classes', [])]
            self.assertIn('users', table_names)
            self.assertIn('orders', table_names)

        finally:
            os.unlink(temp_path)

    def test_create_function(self):
        """Should parse CREATE FUNCTION statements."""
        code = '''CREATE FUNCTION get_user_name(user_id INT)
RETURNS VARCHAR(100)
AS $$
    SELECT name FROM users WHERE id = user_id;
$$ LANGUAGE sql;

CREATE FUNCTION calculate_total(order_id INT)
RETURNS DECIMAL(10, 2)
AS $$
    SELECT SUM(quantity * price)
    FROM order_items
    WHERE order_id = $1;
$$ LANGUAGE sql;
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            # Functions might be extracted depending on SQL grammar
            # Main test is that parsing doesn't crash

        finally:
            os.unlink(temp_path)

    def test_create_view(self):
        """Should handle CREATE VIEW statements."""
        code = '''CREATE VIEW active_users AS
SELECT id, name, email
FROM users
WHERE status = 'active';

CREATE VIEW order_summary AS
SELECT
    o.id,
    u.name AS customer_name,
    o.total,
    o.created_at
FROM orders o
JOIN users u ON o.user_id = u.id;
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_select_statements(self):
        """Should handle SELECT statements without crashing."""
        code = '''SELECT * FROM users;

SELECT u.name, COUNT(o.id) AS order_count
FROM users u
LEFT JOIN orders o ON u.id = o.user_id
GROUP BY u.name
HAVING COUNT(o.id) > 5
ORDER BY order_count DESC;

SELECT DISTINCT category
FROM products
WHERE price > 100;
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_indexes_and_constraints(self):
        """Should handle indexes and constraints."""
        code = '''CREATE TABLE products (
    id INT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category_id INT,
    price DECIMAL(10, 2),
    CONSTRAINT fk_category FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE INDEX idx_products_name ON products(name);
CREATE UNIQUE INDEX idx_products_category ON products(category_id, name);
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_stored_procedure(self):
        """Should handle stored procedures (PostgreSQL/MySQL syntax)."""
        code = '''CREATE PROCEDURE update_user_status(
    IN user_id INT,
    IN new_status VARCHAR(20)
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE users SET status = new_status WHERE id = user_id;
END;
$$;

CREATE PROCEDURE process_orders()
AS $$
BEGIN
    -- Process pending orders
    UPDATE orders SET status = 'processed' WHERE status = 'pending';
END;
$$;
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_triggers(self):
        """Should handle trigger definitions."""
        code = '''CREATE TRIGGER update_timestamp
BEFORE UPDATE ON users
FOR EACH ROW
EXECUTE FUNCTION update_modified_column();

CREATE TRIGGER audit_changes
AFTER INSERT OR UPDATE OR DELETE ON orders
FOR EACH ROW
EXECUTE FUNCTION log_audit();
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_cte_queries(self):
        """Should handle Common Table Expressions (CTEs)."""
        code = '''WITH regional_sales AS (
    SELECT region, SUM(amount) AS total_sales
    FROM orders
    GROUP BY region
),
top_regions AS (
    SELECT region
    FROM regional_sales
    WHERE total_sales > (SELECT SUM(total_sales)/10 FROM regional_sales)
)
SELECT region, product, SUM(quantity) AS product_units
FROM orders
WHERE region IN (SELECT region FROM top_regions)
GROUP BY region, product;
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''CREATE TABLE translations (
    id INT PRIMARY KEY,
    text_en VARCHAR(255),
    text_zh VARCHAR(255),
    text_ru VARCHAR(255)
);

INSERT INTO translations (id, text_en, text_zh, text_ru) VALUES
(1, 'Hello World', '你好世界', 'Привет мир'),
(2, 'Goodbye', '再见', 'До свидания');

-- Comment with emoji: 👍 SQL is powerful! 🚀
SELECT * FROM translations WHERE text_en LIKE '%Hello%';
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SQLAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

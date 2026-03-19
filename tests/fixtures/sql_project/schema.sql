-- Users table
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Categories table
CREATE TABLE categories (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);

-- Posts table with foreign keys
CREATE TABLE posts (
    id INTEGER PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    body TEXT,
    author_id INTEGER NOT NULL,
    category_id INTEGER,
    FOREIGN KEY (author_id) REFERENCES users(id),
    FOREIGN KEY (category_id) REFERENCES categories(id)
);

-- Index on posts
CREATE INDEX idx_posts_author ON posts(author_id);

-- View joining posts and users
CREATE VIEW recent_posts AS
SELECT p.id, p.title, u.name AS author_name
FROM posts p
JOIN users u ON p.author_id = u.id;

-- Function
CREATE FUNCTION update_timestamp() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger
CREATE TRIGGER trg_update_ts
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_timestamp();

-- ALTER TABLE FK
ALTER TABLE posts ADD FOREIGN KEY (editor_id) REFERENCES users(id);

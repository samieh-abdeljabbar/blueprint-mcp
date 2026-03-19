CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    body TEXT,
    author_id INTEGER,
    FOREIGN KEY (author_id) REFERENCES users(id)
);

CREATE VIEW active_users AS
SELECT * FROM users WHERE active = true;

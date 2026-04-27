CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE shifts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  date TEXT NOT NULL,
  type TEXT,
  work TEXT, staff_master_id INTEGER, project TEXT DEFAULT '',
  FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL
);
CREATE TABLE projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,   -- 内部ID
  project_no TEXT NOT NULL UNIQUE,        -- 工事番号
  contract_name TEXT NOT NULL,            -- 契約件名
  start_date TEXT,                        -- 着工日 (YYYY-MM-DD)
  end_date TEXT,                          -- 竣工日 (YYYY-MM-DD)
  change_count INTEGER DEFAULT 0,         -- 設計変更回数
  progress REAL DEFAULT 0,                -- 進捗率 [%]
  manager TEXT,                           -- 担当者
  partner TEXT,                           -- 協力会社
  color TEXT NOT NULL                     -- 表示用カラーコード (#RRGGBB)
, contract_no TEXT);
CREATE TABLE employees (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE NOT NULL,
  department TEXT,
  joined_date TEXT
);
CREATE UNIQUE INDEX idx_users_name ON users(name);

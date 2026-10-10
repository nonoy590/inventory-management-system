-- Inventory System database schema (MySQL)
CREATE DATABASE IF NOT EXISTS inventory_db CHARACTER SET utf8mb4;
USE inventory_db;

CREATE TABLE IF NOT EXISTS items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(100),
    quantity INT NOT NULL DEFAULT 0,
    price DECIMAL(10,2) NOT NULL DEFAULT 0,
    low_stock_threshold INT NOT NULL DEFAULT 5,
    unit VARCHAR(20) NOT NULL DEFAULT 'pcs'
);

CREATE TABLE IF NOT EXISTS sales (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL,
    quantity INT NOT NULL,
    total DECIMAL(10,2) NOT NULL,
    sale_date DATE NOT NULL,
    transaction_id VARCHAR(16),
    buyer_name VARCHAR(100),
    buyer_phone VARCHAR(30),
    created_at DATETIME NULL
);

CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT
);

CREATE TABLE IF NOT EXISTS suppliers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    contact_person VARCHAR(100),
    phone VARCHAR(50),
    email VARCHAR(120),
    address VARCHAR(255)
);

CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    created_at DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_in (
    id INT AUTO_INCREMENT PRIMARY KEY,
    batch_id VARCHAR(16),
    item_id INT,
    product_name VARCHAR(150) NOT NULL,
    quantity INT NOT NULL,
    supplier VARCHAR(150),
    note VARCHAR(255),
    received_date DATE NOT NULL,
    unit_cost DECIMAL(10,2) NOT NULL DEFAULT 0,
    total DECIMAL(10,2) NOT NULL DEFAULT 0,
    created_at DATETIME NULL
);

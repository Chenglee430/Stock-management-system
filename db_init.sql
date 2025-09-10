-- 建立資料庫
CREATE DATABASE IF NOT EXISTS `stock_db` CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE `stock_db`;

-- 建立使用者資料表
CREATE TABLE IF NOT EXISTS `users` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(50) NOT NULL UNIQUE,
    `password` VARCHAR(255) NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 建立使用者登入紀錄表
-- 用於短時間內登入失敗次數的判斷
CREATE TABLE IF NOT EXISTS `login_attempts` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `username` VARCHAR(50) NOT NULL,
    `ip_address` VARCHAR(45) NOT NULL,
    `attempt_time` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 建立股票資料表
CREATE TABLE IF NOT EXISTS `stock_data` (
    `symbol` VARCHAR(20) NOT NULL,
    `company_name` VARCHAR(255) NOT NULL,
    `industry` VARCHAR(255) NOT NULL,
    `date` DATE NOT NULL,
    `open` DECIMAL(10, 2) NULL,
    `high` DECIMAL(10, 2) NULL,
    `low` DECIMAL(10, 2) NULL,
    `close` DECIMAL(10, 2) NULL,
    `volume` BIGINT NULL,
    PRIMARY KEY (`symbol`, `date`),
    INDEX (`industry`) -- 增加產業別索引，加快查詢速度
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 建立使用者查詢紀錄表
-- 由於您限定只能儲存股票代號與日期，我們設計一個簡潔的表格
CREATE TABLE IF NOT EXISTS `user_search_log` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    `user_id` INT UNSIGNED NOT NULL,
    `stock_symbol` VARCHAR(20) NOT NULL,
    `query_date` DATE NOT NULL,
    `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
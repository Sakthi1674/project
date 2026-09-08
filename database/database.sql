-- Attendance Management System Database Schema
-- Database: attendance_system

CREATE DATABASE IF NOT EXISTS attendance_system
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE attendance_system;

-- 1. Persons / Students Table
CREATE TABLE IF NOT EXISTS persons (
    id INT AUTO_INCREMENT PRIMARY KEY,
    person_code VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(100) NOT NULL,
    department VARCHAR(100),
    qr_token VARCHAR(255) UNIQUE,
    qr_code_path VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. QR Sessions Table
CREATE TABLE IF NOT EXISTS qr_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    qr_token VARCHAR(255) NOT NULL UNIQUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    status ENUM('ACTIVE', 'EXPIRED') DEFAULT 'ACTIVE'
) ENGINE=InnoDB;

-- 3. Attendance Table
CREATE TABLE IF NOT EXISTS attendance (
    id INT AUTO_INCREMENT PRIMARY KEY,
    person_id INT NOT NULL,
    qr_session_id INT,
    attendance_date DATE NOT NULL,
    attendance_time TIME NOT NULL,
    status VARCHAR(20) DEFAULT 'PRESENT',

    FOREIGN KEY (person_id)
        REFERENCES persons(id)
        ON DELETE CASCADE,

    FOREIGN KEY (qr_session_id)
        REFERENCES qr_sessions(id)
        ON DELETE SET NULL,

    UNIQUE(person_id, attendance_date)
) ENGINE=InnoDB;

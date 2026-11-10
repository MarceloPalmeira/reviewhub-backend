-- Credenciais exclusivamente de desenvolvimento; não publicar estas portas.
CREATE ROLE identity_service LOGIN PASSWORD 'identity_dev';
CREATE ROLE catalog_service LOGIN PASSWORD 'catalog_dev';
CREATE ROLE reviews_service LOGIN PASSWORD 'reviews_dev';
CREATE DATABASE identity OWNER identity_service;
CREATE DATABASE catalog OWNER catalog_service;
CREATE DATABASE reviews OWNER reviews_service;

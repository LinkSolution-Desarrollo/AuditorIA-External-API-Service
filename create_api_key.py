#!/usr/bin/env python3
"""
Script para crear API Keys para External-API-Service
"""
import os
import sys
import secrets
import hashlib
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from datetime import datetime

# Configuración de la base de datos desde .env o parámetros
DB_URL = os.getenv('DB_URL', 'postgresql://root:password@localhost:5432/auditoria_db')

def create_api_key(name: str):
    """Crea un nuevo API key en la base de datos."""

    # Generar key
    raw_key = secrets.token_urlsafe(32)
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()
    prefix = raw_key[:8]

    # Conectar a la base de datos
    engine = create_engine(DB_URL)

    with engine.connect() as conn:
        # Insertar el API key
        query = text("""
            INSERT INTO global_api_keys (name, hashed_key, prefix, is_active, created_at)
            VALUES (:name, :hashed_key, :prefix, :is_active, :created_at)
            RETURNING id
        """)

        result = conn.execute(query, {
            'name': name,
            'hashed_key': hashed_key,
            'prefix': prefix,
            'is_active': True,
            'created_at': datetime.utcnow()
        })

        conn.commit()
        key_id = result.scalar()

    return {
        'id': key_id,
        'name': name,
        'api_key': raw_key,
        'prefix': prefix
    }

def list_api_keys():
    """Lista todos los API keys activos (sin mostrar la key completa)."""
    engine = create_engine(DB_URL)

    with engine.connect() as conn:
        query = text("""
            SELECT id, name, prefix, created_at, last_used_at
            FROM global_api_keys
            WHERE is_active = true
            ORDER BY created_at DESC
        """)

        results = conn.execute(query)
        return results.fetchall()

def revoke_api_key(key_id: int):
    """Revoca un API key (soft delete)."""
    engine = create_engine(DB_URL)

    with engine.connect() as conn:
        query = text("""
            UPDATE global_api_keys
            SET is_active = false
            WHERE id = :key_id
            RETURNING id
        """)

        result = conn.execute(query, {'key_id': key_id})
        conn.commit()

        if result.rowcount == 0:
            return None
        return key_id

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Gestión de API Keys para External-API')
    subparsers = parser.add_subparsers(dest='command', help='Comandos disponibles')

    # Create command
    create_parser = subparsers.add_parser('create', help='Crear un nuevo API key')
    create_parser.add_argument('name', help='Nombre descriptivo para el API key')

    # List command
    list_parser = subparsers.add_parser('list', help='Listar API keys activos')

    # Revoke command
    revoke_parser = subparsers.add_parser('revoke', help='Revocar un API key')
    revoke_parser.add_argument('key_id', type=int, help='ID del API key a revocar')

    args = parser.parse_args()

    if args.command == 'create':
        print(f"[*] Creando API Key '{args.name}'...")
        try:
            result = create_api_key(args.name)
            print("\n[OK] API Key creado exitosamente!")
            print(f"=" * 60)
            print(f"ID:       {result['id']}")
            print(f"Nombre:   {result['name']}")
            print(f"Prefijo:  {result['prefix']}...")
            print(f"=" * 60)
            print(f"\n[!] GUARDA ESTE API KEY - NO SE MOSTRARA NUEVAMENTE:")
            print(f"\n{result['api_key']}")
            print(f"\n" + "=" * 60)
            print(f"\n[+] Uso en tus requests:")
            print(f"   curl -H \"X-API-Key: {result['api_key']}\" http://localhost:8001/campaigns/")
            print()
        except Exception as e:
            print(f"[ERROR] Error: {e}")
            sys.exit(1)

    elif args.command == 'list':
        print("[*] API Keys activos:\n")
        try:
            keys = list_api_keys()
            if not keys:
                print("No hay API keys activos.")
            else:
                for key in keys:
                    print(f"ID: {key[0]}")
                    print(f"  Nombre:     {key[1]}")
                    print(f"  Prefijo:    {key[2]}...")
                    print(f"  Creado:     {key[3]}")
                    print(f"  Ultimo uso: {key[4] or 'Nunca'}")
                    print()
        except Exception as e:
            print(f"[ERROR] Error: {e}")
            sys.exit(1)

    elif args.command == 'revoke':
        print(f"[*] Revocando API Key ID {args.key_id}...")
        try:
            result = revoke_api_key(args.key_id)
            if result:
                print(f"[OK] API Key {args.key_id} revocado exitosamente.")
            else:
                print(f"[ERROR] API Key {args.key_id} no encontrado.")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Error: {e}")
            sys.exit(1)

    else:
        parser.print_help()

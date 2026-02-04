#!/usr/bin/env python3
"""Test script to verify .env loading."""

import os
from pathlib import Path

# Change to project directory
os.chdir(Path(__file__).parent)

# Load .env like the CLI does
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

# Check if key is loaded
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    print("❌ OPENAI_API_KEY not found in environment")
    print("   Make sure .env file exists and contains: OPENAI_API_KEY=sk-...")
elif api_key == "your-openai-api-key-here":
    print("⚠️  OPENAI_API_KEY is still the placeholder value")
    print("   Edit .env and replace with your actual key")
else:
    print(f"✅ OPENAI_API_KEY is set (length: {len(api_key)} chars)")
    print(f"   Starts with: {api_key[:10]}...")
    print("\n✅ LLM detection will work correctly!")

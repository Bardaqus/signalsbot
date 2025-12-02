#!/usr/bin/env python3
"""
Setup script for Signals_bot
"""
import os
import sys
from pathlib import Path


def create_env_file():
    """Create .env file from template"""
    env_file = Path('.env')
    template_file = Path('config_example.env')
    
    if env_file.exists():
        print("⚠️  .env file already exists!")
        response = input("Do you want to overwrite it? (y/N): ")
        if response.lower() != 'y':
            print("Keeping existing .env file")
            return
    
    if not template_file.exists():
        print("❌ config_example.env not found!")
        return
    
    # Copy template to .env
    with open(template_file, 'r') as f:
        content = f.read()
    
    with open(env_file, 'w') as f:
        f.write(content)
    
    print("✅ Created .env file from template")
    print("📝 Please edit .env file with your actual credentials")


def create_directories():
    """Create necessary directories"""
    directories = ['logs', 'data']
    
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"📁 Created directory: {directory}")


def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ is required!")
        print(f"Current version: {version.major}.{version.minor}.{version.micro}")
        return False
    
    print(f"✅ Python version: {version.major}.{version.minor}.{version.micro}")
    return True


def install_dependencies():
    """Install required dependencies"""
    print("📦 Installing dependencies...")
    os.system(f"{sys.executable} -m pip install -r requirements.txt")
    print("✅ Dependencies installed")


def main():
    """Main setup function"""
    print("🚀 Setting up Signals Bot...")
    print("=" * 50)
    
    # Check Python version
    if not check_python_version():
        sys.exit(1)
    
    # Create directories
    create_directories()
    
    # Create .env file
    create_env_file()
    
    # Install dependencies
    install_dependencies()
    
    print("\n" + "=" * 50)
    print("🎉 Setup completed!")
    print("\n📋 Next steps:")
    print("1. Edit .env file with your credentials:")
    print("   - Telegram bot token from @BotFather")
    print("   - cTrader API credentials from Spotware Connect")
    print("   - Demo account details")
    print("2. Run the bot: python main.py")
    print("3. Or use the startup script: ./run_bot.sh")
    print("\n📖 For more information, see README.md")


if __name__ == "__main__":
    main()


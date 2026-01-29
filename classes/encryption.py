"""
Encryption utilities for Roblox Account Manager
Handles hardware-based and password-based encryption
"""

import os
import json
import base64
import hashlib
import platform
import subprocess
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Protocol.KDF import PBKDF2


class HardwareEncryption:
    """Hardware-based encryption using machine-specific identifiers"""
    
    def __init__(self):
        self.machine_id = self._get_machine_id()
        self.key = self._derive_key_from_machine_id()
    
    def _get_machine_id(self):
        """Generate unique machine ID from hardware identifiers"""
        identifiers = []
        
        try:
            if platform.system() == "Windows":
                result = subprocess.check_output("wmic csproduct get uuid", shell=True)
                uuid = result.decode().split('\n')[1].strip()
                identifiers.append(uuid)
                
                result = subprocess.check_output("wmic cpu get processorid", shell=True)
                cpu_id = result.decode().split('\n')[1].strip()
                identifiers.append(cpu_id)
                
                result = subprocess.check_output("wmic baseboard get serialnumber", shell=True)
                board_serial = result.decode().split('\n')[1].strip()
                identifiers.append(board_serial)
            else:
                identifiers.append(platform.node())
                identifiers.append(str(os.getuid()) if hasattr(os, 'getuid') else "0")
        except:
            identifiers.append(platform.node())
            identifiers.append(platform.machine())
        
        machine_string = "-".join(identifiers)
        return hashlib.sha256(machine_string.encode()).hexdigest()
    
    def _derive_key_from_machine_id(self):
        """Derive encryption key from machine ID"""
        salt = b'roblox_account_manager_salt_v1'
        key = PBKDF2(self.machine_id, salt, dkLen=32, count=100000)
        return key
    
    def encrypt_data(self, data):
        """Encrypt data using hardware-based key"""
        if isinstance(data, dict):
            data = json.dumps(data, indent=2, ensure_ascii=False)
        
        data_bytes = data.encode('utf-8')
        
        cipher = AES.new(self.key, AES.MODE_GCM)
        nonce = cipher.nonce
        
        ciphertext, tag = cipher.encrypt_and_digest(data_bytes)
        
        encrypted_package = {
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8')
        }
        
        return encrypted_package
    
    def decrypt_data(self, encrypted_package):
        """Decrypt data using hardware-based key"""
        try:
            nonce = base64.b64decode(encrypted_package['nonce'])
            tag = base64.b64decode(encrypted_package['tag'])
            ciphertext = base64.b64decode(encrypted_package['ciphertext'])
            
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
            
            data_bytes = cipher.decrypt_and_verify(ciphertext, tag)
            
            data_string = data_bytes.decode('utf-8')
            
            try:
                return json.loads(data_string)
            except:
                return data_string
                
        except Exception as e:
            raise Exception("Decryption failed. This program may have been encrypted on a different machine.")


class PasswordEncryption:
    """Password-based encryption for portable account data"""
    
    def __init__(self, password, salt=None):
        if salt is None:
            self.salt = get_random_bytes(32)
        else:
            if isinstance(salt, str):
                self.salt = base64.b64decode(salt)
            else:
                self.salt = salt
        
        self.key = self._derive_key_from_password(password)
    
    def _derive_key_from_password(self, password):
        """Derive encryption key from password"""
        key = PBKDF2(password, self.salt, dkLen=32, count=100000)
        return key
    
    def get_salt_b64(self):
        """Get base64-encoded salt"""
        return base64.b64encode(self.salt).decode('utf-8')
    
    def encrypt_data(self, data):
        """Encrypt data using password-based key"""
        if isinstance(data, dict):
            data = json.dumps(data, indent=2, ensure_ascii=False)
        
        data_bytes = data.encode('utf-8')
        
        cipher = AES.new(self.key, AES.MODE_GCM)
        nonce = cipher.nonce
        
        ciphertext, tag = cipher.encrypt_and_digest(data_bytes)
        
        encrypted_package = {
            'nonce': base64.b64encode(nonce).decode('utf-8'),
            'tag': base64.b64encode(tag).decode('utf-8'),
            'ciphertext': base64.b64encode(ciphertext).decode('utf-8')
        }
        
        return encrypted_package
    
    def decrypt_data(self, encrypted_package):
        """Decrypt data using password-based key"""
        try:
            nonce = base64.b64decode(encrypted_package['nonce'])
            tag = base64.b64decode(encrypted_package['tag'])
            ciphertext = base64.b64decode(encrypted_package['ciphertext'])
            
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
            
            data_bytes = cipher.decrypt_and_verify(ciphertext, tag)
            
            data_string = data_bytes.decode('utf-8')
            
            try:
                return json.loads(data_string)
            except:
                return data_string
                
        except Exception as e:
            raise Exception(f"Decryption failed. Password may be incorrect. Error: {str(e)}")


class EncryptionConfig:
    """Manages encryption configuration and settings"""
    
    def __init__(self, config_file="encryption_config.json"):
        self.config_file = config_file
        self.config = self._load_config()
    
    def _load_config(self):
        """Load encryption configuration from file"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_config(self):
        """Save encryption configuration to file"""
        config_dir = os.path.dirname(self.config_file)
        if config_dir and not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2, ensure_ascii=False)
    
    def is_encryption_enabled(self):
        """Check if encryption is enabled"""
        return self.config.get('encryption_enabled', False)
    
    def is_setup_complete(self):
        """Check if encryption setup has been completed"""
        if self.config.get('setup_completed', False):
            return True
        if 'encryption_method' in self.config or 'encryption_enabled' in self.config:
            return True
        return False
    
    def get_encryption_method(self):
        """Get current encryption method"""
        return self.config.get('encryption_method', None)
    
    def get_salt(self):
        """Get stored salt for password encryption"""
        return self.config.get('salt', None)
    
    def get_password_hash(self):
        """Get stored password hash"""
        return self.config.get('password_hash', None)
    
    def enable_hardware_encryption(self):
        """Enable hardware-based encryption"""
        self.config['encryption_enabled'] = True
        self.config['encryption_method'] = 'hardware'
        self.config['setup_completed'] = True
        self.save_config()
    
    def enable_password_encryption(self, salt, password_hash):
        """Enable password-based encryption"""
        self.config['encryption_enabled'] = True
        self.config['encryption_method'] = 'password'
        self.config['salt'] = salt
        self.config['password_hash'] = password_hash
        self.config['password_verified'] = True
        self.config['setup_completed'] = True
        self.save_config()
    
    def is_password_verified(self):
        """Check if password has been verified with actual data"""
        return self.config.get('password_verified', False)
    
    def disable_encryption(self):
        """Disable encryption"""
        self.config['encryption_enabled'] = False
        self.config['encryption_method'] = None
        self.config['setup_completed'] = True
        if 'salt' in self.config:
            del self.config['salt']
        self.save_config()
    
    def reset_encryption(self):
        """Reset encryption settings completely"""
        self.config.clear()
        self.save_config()
    
    def set_encryption_method(self, method):
        """Set encryption method without data"""
        if method == 'hardware':
            self.enable_hardware_encryption()
        elif method == 'password':
            pass
        else:
            raise ValueError(f"Invalid encryption method: {method}")

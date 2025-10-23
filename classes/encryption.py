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
        return base64.b64encode(self.salt).decode('utf-8')

    def encrypt_data(self, data):
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
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def save_config(self):
        return self.config.get('encryption_enabled', False)

    def get_encryption_method(self):
        return self.config.get('salt', None)

    def get_password_hash(self):
        self.config['encryption_enabled'] = True
        self.config['encryption_method'] = 'hardware'
        self.save_config()

    def enable_password_encryption(self, salt, password_hash):
        return self.config.get('password_verified', False)

    def disable_encryption(self):

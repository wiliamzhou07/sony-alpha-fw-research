# aes_single_key_decrypt.py
from Crypto.Cipher import AES

def main():
    import sys
    # 硬编码 key_aes
    key_aes = b'\xE3\xB0\xC4\x42\x98\xFC\x1C\x14\x9A\xFB\xF4\xC8\x99\x6F\xB9\x24'

    if len(sys.argv) != 2:
        print("用法: python aes_single_key_decrypt.py <固件bin路径>")
        sys.exit(1)

    fw_path = sys.argv[1]
    out_path = fw_path + ".dec.full.bin"

    with open(fw_path, "rb") as f:
        data = f.read()

    # 整份文件一次性 AES-ECB 解密
    cipher = AES.new(key_aes, AES.MODE_ECB)
    dec_data = cipher.decrypt(data)

    with open(out_path, "wb") as fo:
        fo.write(dec_data)

    print(f"解密完成，输出文件: {out_path}")
    print(f"原始长度: {len(data)} bytes")
    print(f"解密长度: {len(dec_data)} bytes")

if __name__ == "__main__":
    main()

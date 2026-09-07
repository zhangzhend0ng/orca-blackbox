import base64, sys
src, dst = sys.argv[1], sys.argv[2]
data = open(src, 'rb').read()
enc = base64.b64encode(data).decode()
with open(dst, 'w') as f:
    f.write('\n'.join(enc[i:i+76] for i in range(0, len(enc), 76)))
print('LINES', enc and (len(enc) + 75) // 76)

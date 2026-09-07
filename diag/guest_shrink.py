import sys, cv2
src, dst = sys.argv[1], sys.argv[2]
img = cv2.imread(src)
h, w = img.shape[:2]
scale = 460.0 / w
img = cv2.resize(img, (460, int(h * scale)))
cv2.imwrite(dst, img, [cv2.IMWRITE_JPEG_QUALITY, 82])
print('shrunk', img.shape)

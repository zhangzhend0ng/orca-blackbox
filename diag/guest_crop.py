import sys, cv2
src, dst, x0, y0, x1, y1 = sys.argv[1], sys.argv[2], *map(int, sys.argv[3:7])
img = cv2.imread(src)
crop = img[y0:y1, x0:x1]
cv2.imwrite(dst, crop, [cv2.IMWRITE_JPEG_QUALITY, 90])
print('crop', crop.shape)

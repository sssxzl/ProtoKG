# -*- coding: utf-8 -*-
import zipfile, re, sys
p = sys.argv[1]
z = zipfile.ZipFile(p)
xml = z.read('word/document.xml').decode('utf-8', 'ignore')
# 按段落/表格拆分
# 先把表格单元格分隔开，便于阅读
xml = xml.replace('</w:tc>', '\n</w:tc>')
# 段落结束标记
xml = xml.replace('</w:p>', '\n')
text = re.sub(r'<[^>]+>', '', xml)
text = re.sub(r'\n\s*\n+', '\n', text)
print(text)

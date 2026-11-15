import csv, json, sys, os
src = os.path.join('..','results','for_friend')
def load(n):
    with open(os.path.join(src,n),encoding='utf-8-sig',newline='') as f:
        r=list(csv.DictReader(f)); return r
data={'pilot':load('L2_pilot_sheet.csv'),'main':load('L2_main_sheet.csv')}
hdr=list(data['main'][0].keys())
blob=json.dumps({'header':hdr,'sets':data},ensure_ascii=False).replace('</','<\\/')
html=open('template.html',encoding='utf-8').read().replace('/*DATA*/null',blob)
open('LABEL_TOOL.html','w',encoding='utf-8').write(html)
print('ok',len(html)//1024,'KB',{k:len(v) for k,v in data.items()})

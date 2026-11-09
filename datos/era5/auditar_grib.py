"""Recupera selecciones CDS de los encabezados GRIB1 sin decodificar los campos."""
import argparse
import json
from datetime import datetime,timedelta
from collections import defaultdict
from pathlib import Path

def number(data):
    return int.from_bytes(data, "big")

def angle(data):
    n = number(data)
    return (-(n & 0x7fffff) if n & 0x800000 else n) / 1000

def inspect(path,src):
    by_field = defaultdict(set)
    total = path.stat().st_size
    count = 0
    with path.open("rb") as raw:
        offset = 0
        while offset < total:
            raw.seek(offset)
            data = raw.read(320)
            assert data[:4] == b"GRIB" and data[7] == 1, (path, offset)
            length = number(data[4:7])
            assert length > 100 and offset + length <= total
            offset += length
            p = data[8:]
            g = p[number(p[:3]):]
            assert p[4] == 98 and p[7] & 128 and g[5] == 0, (path,offset,p[:12].hex(),g[:10].hex())
            assert p[16] == 0 and p[17] == 1 and p[20] in (0,2,3,4,10), (path, p[:26].hex())
            area = (angle(g[10:13]), angle(g[13:16]), angle(g[17:20]), angle(g[20:23]))
            grid = (number(g[23:25])/1000, number(g[25:27])/1000)
            assert len(g)>=32 and all(grid) and all(number(g[i:i+2])>1 for i in (6,8))
            assert abs((area[0]-area[2])/(number(g[8:10])-1) - grid[1]) < 1e-6
            assert abs((area[3]-area[1])/(number(g[6:8])-1) - grid[0]) < 1e-6
            year = (p[24]-1)*100+p[12]
            level = number(p[10:12]) if p[9] == 100 else None
            param = p[8] if p[3] == 128 else p[3]*1000+p[8]
            step = p[18] if p[20]==0 else number(p[18:20]) if p[20]==10 else p[19]
            valid = datetime(year,p[13],p[14],p[15])+timedelta(hours=step)
            by_field[(area, grid, param, level)].add((valid.year,valid.month,valid.day,valid.hour))
            count += 1
    # Group only variables/levels with precisely the same dates and times.
    groups = defaultdict(list)
    for (area, grid, var, lev), times in by_field.items():
        groups[(area,grid,frozenset(times),var)].append(lev)
    sets = defaultdict(list)
    for (area, grid, times, var), levels in groups.items():
        sets[(area,grid,times,tuple(sorted(levels)))].append(var)
    requests = []
    for (area,grid,times,levels), ids in sets.items():
        dates = defaultdict(list)
        for y,m,d,h in sorted(times):
            dates[y,m,d].append(h)
        months = defaultdict(list)
        for (y,m,d),hs in dates.items():
            months[y,m,tuple(hs)].append(d)
        for (y,m,hs),ds in sorted(months.items()):
            requests.append(dict(area=area,grid=grid,parameter_ids=sorted(ids),
                                 pressure_level=list(levels) if levels!=(None,) else [],
                                 year=y,month=m,day=ds,time=hs))
    expected=sum(len(s["parameter_ids"])*(len(s["pressure_level"]) or 1)*len(s["day"])*len(s["time"]) for s in requests)
    assert count == expected, (path,count,expected)
    return dict(archivo=path.relative_to(src).as_posix(),bytes=total,mensajes=count,selecciones=requests)

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("carpeta",type=Path)
    parser.add_argument("inventario",type=Path)
    args=parser.parse_args()
    src=args.carpeta
    rows=[]
    for path in sorted(src.rglob("*.grib")):
        item=inspect(path,src)
        print(path.name,item["mensajes"],len(item["selecciones"]),flush=True)
        rows.append(item)
    args.inventario.write_text(json.dumps(rows,ensure_ascii=False,indent=1),encoding="utf8")

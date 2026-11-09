"""Exportación BASE; convierte numpy.str_ explícitamente a str para pandas.
El preparador original y su diseño permanecen congelados.
"""
from preparar_base_verano_20261021 import *

def export():
    verify(read(OUT/'Preparacion.json')['archivos'])
    plan=read(OUT/'Plan.json')
    cache=OUT/'Exportacion_parcial.json';items=read(cache) if cache.exists() else []
    saved={Path(r['original']['path']).name:r for r in items}
    earlier={Path(r['original']).name:r for r in read(CHAIN/'QA_WRF.json')['archivos']}
    for item in plan['fuentes_WRF']:
        name=item['archivo'];src=Path(item['path']);dst=OUT/'WRF_BASE'/name
        if name in saved:
            verify([saved[name]['exportado']]);continue
        assert not dst.exists(),'Exportación sin recepción: '+str(dst)
        assert sha256(src)==item['sha256'],'Original WRF cambiado'
        ix=item['indices_seleccionados'];s=slice(ix[0],ix[-1]+1)
        assert ix==list(range(ix[0],ix[-1]+1))
        print('Exportando/verificando '+name,flush=True)
        reused=False
        old=earlier.get(name)
        # Copias ordinarias: el entorno no permite crear enlaces duros.
        # La estimación previa de espacio cubre todos los archivos nuevos.
        with Dataset(src) as n:
            n.set_auto_mask(False)
            missing=set(KEEP)-set(n.variables);assert not missing-OPTIONAL
            assert abs(float(n['XLAT'][0,43,42])+33.15632248)<1e-5
            assert abs(float(n['XLONG'][0,43,42])+70.29452515)<1e-5
            assert abs(float(n['HGT'][0,43,42])-3469.60400390625)<.01
            assert int(n['LU_INDEX'][0,43,42]) not in (int(n.ISWATER),int(n.ISLAKE))
            if not reused:
                with Dataset(dst,'w',format='NETCDF3_64BIT_OFFSET') as d:
                    d.setncatts({a:n.getncattr(a) for a in n.ncattrs()})
                    for key,dim in n.dimensions.items():d.createDimension(key,None if key=='Time' else len(dim))
                    for key in KEEP:
                        if key not in n.variables:continue
                        v=n[key];w=d.createVariable(key,v.dtype,v.dimensions,fill_value=getattr(v,'_FillValue',False))
                        w.setncatts({a:v.getncattr(a) for a in v.ncattrs() if a!='_FillValue'})
                    for key in d.variables:
                        v=n[key];d[key][:]=v[s] if 'Time' in v.dimensions else v[:]
            with Dataset(dst) as d:
                d.set_auto_mask(False)
                assert set(d.variables)==set(KEEP)-missing
                for key,v in d.variables.items():
                    expected=n[key][s] if 'Time' in v.dimensions else n[key][:]
                    assert np.array_equal(expected,v[:],equal_nan=v.dtype.kind=='f'),key
                    if v.dtype.kind=='f':assert np.isfinite(v[:]).all(),key
                q=np.asarray(d['Q2'][:]);qv=np.asarray(d['QVAPOR'][:])
                near=q[:,42:45,41:44]
                p=np.asarray(d['P'][:])+np.asarray(d['PB'][:])
                qa=dict(Q2_min_punto=float(q[:,43,42].min()),Q2_min_3x3=float(near.min()),
                    Q2_negativas_dominio=int((q<0).sum()),QVAPOR_min_3x3=float(qv[:,:,42:45,41:44].min()),
                    QVAPOR_negativas_dominio=int((qv<0).sum()),presion_min_Pa=float(p.min()),
                    T2_punto_min_K=float(d['T2'][:,43,42].min()),T2_punto_max_K=float(d['T2'][:,43,42].max()),
                    PBLH_punto_min_m=float(d['PBLH'][:,43,42].min()))
                assert qa['Q2_min_3x3']>=0 and qa['QVAPOR_min_3x3']>=0 and qa['presion_min_Pa']>0,qa
                assert 150<qa['T2_punto_min_K']<=qa['T2_punto_max_K']<350 and qa['PBLH_punto_min_m']>0,qa
                stamps=list(chartostring(d['Times'][:]))
        entries=dict(original=dict(path=str(src),sha256=item['sha256']),exportado=record(dst),
            bytes=dst.stat().st_size,indices=ix,Times=stamps,QA=qa,enlace_inmutable_previo=reused)
        items.append(entries);guardar_json(cache,items)
    actual=[pd.Timestamp(t.replace('_',' ')) for row in items for t in row['Times']]
    assert pd.DatetimeIndex(actual).equals(pd.date_range(AUX+pd.Timedelta(hours=3),END+pd.Timedelta(hours=3),freq='h'))
    guardar_json(OUT/'Exportacion.json',dict(estado='BASE_NETCDF3_VERIFICADO',archivos=items,instantes=len(actual),
        nota='Campos exportados idénticos al original; Q2 externa negativa documentada, celda y3x3 válidos. No valida todo el estado atmosférico.',
        bytes_logicos=sum(r['bytes'] for r in items),bytes_nuevos=sum(r['bytes'] for r in items if not r['enlace_inmutable_previo'])))
    print('BASE estacional exportado y verificado.',flush=True)

if __name__=="__main__":
    export()

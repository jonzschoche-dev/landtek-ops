# Run in QGIS: Plugins > Python Console > Show Editor > open this file > Run.
# Loads the MWK / T-4497 map over satellite imagery and saves MWK_T4497.qgz next to this file.
import os
from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer, QgsRuleBasedRenderer, QgsFillSymbol,
                       QgsMarkerSymbol, QgsPalLayerSettings, QgsVectorLayerSimpleLabeling, QgsTextFormat,
                       QgsCoordinateReferenceSystem)
from qgis.PyQt.QtGui import QColor
HERE = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.path.expanduser(
    '~/landtek/case_work/MWK-001/GIS_2026-10')
P = QgsProject.instance(); P.clear()
P.setCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
sat = QgsRasterLayer('type=xyz&url=https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/%7Bz%7D/%7By%7D/%7Bx%7D&zmax=19&zmin=0', 'Esri World Imagery', 'wms')
P.addMapLayer(sat)
lots = QgsVectorLayer(os.path.join(HERE, 'mwk_parcels.geojson'), 'MWK parcels (T-4497)', 'ogr')
rules = [
    ('T-4497 mother title (Lot 2)', '"title" = \'T-4497\'', '#ffffff', 1.6),
    ('Spec. Proc. 2156 titles', '"sp2156" = true', '#ff3b30', 0.9),
    ('Lot 2-X (1975 parent)', '"parcel_code" = \'MWK-PSD221861-X\'', '#ffffff', 0.8),
    ('Lot 2-X-6 (T-32917)', '"title" = \'T-32917\'', '#ff9500', 0.8),
    ('Titles mapped from own courses', '"source" = \'own title courses + tie\'', '#ffcc00', 0.5),
    ('1975 lots Psd-221861', '"parcel_code" LIKE \'MWK-PSD221861-%\'', '#5ac8fa', 0.5),
    ('Other plotted', 'ELSE', '#34c759', 0.6),
]
root = QgsRuleBasedRenderer.Rule(None)
for name, expr, col, w in rules:
    sym = QgsFillSymbol.createSimple({'color': '0,0,0,0', 'outline_color': col, 'outline_width': str(w)})
    r = QgsRuleBasedRenderer.Rule(sym, label=name)
    if expr == 'ELSE': r.setIsElse(True)
    else: r.setFilterExpression(expr)
    root.appendChild(r)
lots.setRenderer(QgsRuleBasedRenderer(root))
pal = QgsPalLayerSettings(); pal.fieldName = 'coalesce("lot", \'\') || \' · \' || coalesce("title", "parcel_code")'; pal.isExpression = True
fmt = QgsTextFormat(); fmt.setColor(QColor('white')); fmt.setSize(8); fmt.buffer().setEnabled(True); fmt.buffer().setColor(QColor('black'))
pal.setFormat(fmt); lots.setLabeling(QgsVectorLayerSimpleLabeling(pal)); lots.setLabelsEnabled(True)
P.addMapLayer(lots)

cdf = QgsVectorLayer(os.path.join(HERE, 'mwk_parcels.geojson'), 'Cesar dela Fuente sales', 'ogr')
cdf.setSubsetString('"cdf" IS NOT NULL')
croot = QgsRuleBasedRenderer.Rule(None)
for name, expr, props in [
    ('Deed of sale signed by dela Fuente', '"cdf" = \'deed\'', {'color': '255,0,200,170', 'outline_color': '#ff00c8', 'outline_width': '0.8'}),
    ('Dela Fuente confirmation of an earlier sale', '"cdf" = \'confirmation\'', {'color': '255,149,0,140', 'outline_color': '#ff9500', 'outline_width': '0.6'}),
    ('Sold in his era, signer not named', '"cdf" = \'probable\'', {'color': '255,204,0,0', 'outline_color': '#ffcc00', 'outline_width': '0.6', 'style': 'b_diagonal'}),
]:
    sym = QgsFillSymbol.createSimple(props)
    r = QgsRuleBasedRenderer.Rule(sym, label=name); r.setFilterExpression(expr); croot.appendChild(r)
cdf.setRenderer(QgsRuleBasedRenderer(croot))
cpal = QgsPalLayerSettings(); cpal.fieldName = 'coalesce("lot",\'\') || \' · \' || coalesce("cdf_buyer",\'\')'; cpal.isExpression = True
cfmt = QgsTextFormat(); cfmt.setColor(QColor('#ffe0f7')); cfmt.setSize(8); cfmt.buffer().setEnabled(True); cfmt.buffer().setColor(QColor('black'))
cpal.setFormat(cfmt); cdf.setLabeling(QgsVectorLayerSimpleLabeling(cpal)); cdf.setLabelsEnabled(True)
P.addMapLayer(cdf)

llam = QgsVectorLayer(os.path.join(HERE, 'mwk_parcels.geojson'), 'Started by Llamanzares, finished by dela Fuente', 'ogr')
llam.setSubsetString('"origin" = \'llamanzares_start\'')
llam.renderer().setSymbol(QgsFillSymbol.createSimple({'color': '0,229,255,90', 'outline_color': '#00e5ff', 'outline_width': '1.4'}))
lpal = QgsPalLayerSettings(); lpal.fieldName = '"lot" || \' · \' || "cdf_buyer" || \' (Llamanzares deed → dela Fuente)\''; lpal.isExpression = True
lfmt = QgsTextFormat(); lfmt.setColor(QColor('#bff8ff')); lfmt.setSize(9); lfmt.buffer().setEnabled(True); lfmt.buffer().setColor(QColor('black'))
lpal.setFormat(lfmt); llam.setLabeling(QgsVectorLayerSimpleLabeling(lpal)); llam.setLabelsEnabled(True)
P.addMapLayer(llam)
cdft = QgsVectorLayer('file://' + os.path.join(HERE, 'CDF_SALES.csv') + '?type=csv&geomType=none', 'Dela Fuente sales (incl. unmapped)', 'delimitedtext')
P.addMapLayer(cdft)
mon = QgsVectorLayer(os.path.join(HERE, 'monuments.geojson'), 'Survey monuments (solved)', 'ogr')
mon.renderer().setSymbol(QgsMarkerSymbol.createSimple({'name': 'triangle', 'color': '#34c759', 'size': '4'}))
P.addMapLayer(mon)
status = QgsVectorLayer('file://' + os.path.join(HERE, 'LOT_2X_TITLE_STATUS.csv') + '?type=csv&geomType=none', 'T-4497 title status', 'delimitedtext')
P.addMapLayer(status)
P.write(os.path.join(HERE, 'MWK_T4497.qgz'))
iface.mapCanvas().setExtent(iface.mapCanvas().mapSettings().layerToMapCoordinates(lots, lots.extent()))
iface.mapCanvas().refresh()
print('Saved', os.path.join(HERE, 'MWK_T4497.qgz'))

(function(){
const edit=document.getElementById('edit-map'), detail=document.getElementById('detail-map');
let syncMap=()=>{};
const direction=document.getElementById('id_direction');
if(direction){
 direction.addEventListener('change',()=>{
  for(const field of ['area','lat','lon']){
   const a=document.getElementById('id_origin_'+field),b=document.getElementById('id_destination_'+field);
   [a.value,b.value]=[b.value,a.value];
  }
  const pickup=document.getElementById('id_pickup_private'),destination=document.getElementById('id_destination_private');
  if(pickup&&destination)[pickup.value,destination.value]=[destination.value,pickup.value];
  syncMap();
 });
}
if(!window.L || (!edit && !detail))return;
const box=edit||detail;
const map=L.map(box).setView([49.94,14.58],10);
const tiles=L.tileLayer('/openride/tiles/{z}/{x}/{y}.png',{maxZoom:19,attribution:'Powered by <a href="https://www.geoapify.com/">Geoapify</a> | © <a href="https://openmaptiles.org/">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'}).addTo(map);
tiles.on('tileerror',()=>{document.getElementById('map-error').textContent='Mapové podklady jsou dočasně nedostupné. Textové údaje zůstávají dostupné.'});
if(edit){
 let next='origin', markers={};
 function setPoint(which,lat,lon){
  document.getElementById('id_'+which+'_lat').value=lat.toFixed(6);
  document.getElementById('id_'+which+'_lon').value=lon.toFixed(6);
  if(markers[which])map.removeLayer(markers[which]);
  markers[which]=L.marker([lat,lon]).addTo(map).bindPopup(which==='origin'?'Výchozí bod':'Cílový bod');
  next=which==='origin'?'destination':'origin';
  document.getElementById('map-hint').textContent='Další kliknutí nastaví '+(next==='origin'?'výchozí':'cílový')+' bod.';
 }
 ['origin','destination'].forEach(which=>{
  const lat=parseFloat(document.getElementById('id_'+which+'_lat').value),lon=parseFloat(document.getElementById('id_'+which+'_lon').value);
  if(Number.isFinite(lat)&&Number.isFinite(lon)){setPoint(which,lat,lon);map.setView([lat,lon],12)}
  const input=document.getElementById('id_'+which+'_area'),list=document.querySelector('[data-for="'+which+'_area"]');let timer;
  input.addEventListener('input',()=>{clearTimeout(timer);list.replaceChildren();if(input.value.trim().length<3)return;timer=setTimeout(async()=>{
    try{const r=await fetch('/openride/places/?q='+encodeURIComponent(input.value.trim()));const d=await r.json();if(d.error){list.textContent=d.error;return}d.results.forEach(x=>{const b=document.createElement('button');b.type='button';b.textContent=x.label;b.onclick=()=>{input.value=x.label;setPoint(which,x.lat,x.lon);map.setView([x.lat,x.lon],12);list.replaceChildren()};list.append(b)})}
    catch{list.textContent='Vyhledávání je nedostupné.'}
  },350)})
 });
 syncMap=()=>{
  for(const marker of Object.values(markers))map.removeLayer(marker);
  markers={};
  const points=[];
  for(const which of ['origin','destination']){
   const lat=parseFloat(document.getElementById('id_'+which+'_lat').value),lon=parseFloat(document.getElementById('id_'+which+'_lon').value);
   if(Number.isFinite(lat)&&Number.isFinite(lon)){setPoint(which,lat,lon);points.push([lat,lon])}
  }
  if(points.length===2)map.fitBounds(L.latLngBounds(points).pad(.25));
  else if(points.length===1)map.setView(points[0],12);
  next=direction.value==='to'?'origin':'destination';
  document.getElementById('map-hint').textContent='Další kliknutí nastaví '+(next==='origin'?'výchozí':'cílový')+' bod.';
 };
 map.on('click',e=>setPoint(next,e.latlng.lat,e.latlng.lng));
}
if(detail){
 const id=box.dataset.id,info=document.getElementById('route-info');
 fetch('/openride/map/'+id+'/').then(r=>r.json()).then(async d=>{
  const pts=[d.origin,d.destination].filter(Boolean);
  pts.forEach((p,i)=>L.marker(p).addTo(map).bindPopup(i===0?'Výchozí oblast':'Cílová oblast'));
  (d.stops||[]).forEach(s=>{if(s.lat!=null&&s.lon!=null)L.circleMarker([s.lat,s.lon],{radius:7,color:'#bd7b4d'}).addTo(map).bindPopup(s.area||s.label||'Zastávka')});
  if(pts.length===2)map.fitBounds(L.latLngBounds(pts).pad(.25));
  if(pts.length<2){info.textContent='Souřadnice nejsou zadané. Použij textový přehled cesty.';return}
  try{const r=await fetch('/openride/route/'+id+'/');const route=await r.json();if(!r.ok)throw Error(route.error||'Výpočet trasy je nedostupný.');
   const line=L.geoJSON(route.geometry,{style:{color:d.kind==='demand'?'#bd7b4d':'#276b58',weight:5,dashArray:route.approximate?'8 7':null}}).addTo(map);map.fitBounds(line.getBounds().pad(.15));
   info.textContent=(route.approximate?'Orientační trasa · ':'Trasa autem · ')+(route.distance_m/1000).toFixed(1)+' km · asi '+Math.round(route.duration_s/60)+' min.';
  }catch(e){info.textContent=e.message+' Textový přehled cesty zůstává dostupný.'}
 }).catch(()=>{info.textContent='Mapová data jsou dočasně nedostupná. Textový přehled cesty zůstává dostupný.'})
}
})();

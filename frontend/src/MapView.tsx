import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Crosshair, Expand, Map as MapIcon, LocateFixed, Shrink, ExternalLink } from 'lucide-react'
import { api, type Fix } from './api'

const mapFiles:Record<string,string>={'ZJGroute.txt':'zjg','ZJGWestTrack.geojson':'zjg','YQroute.txt':'yuquan','HNroute.txt':'haining'}
const routeNames:Record<string,string>={'ZJGroute.txt':'紫金港','ZJGWestTrack.geojson':'紫金港西田径场','YQroute.txt':'玉泉','HNroute.txt':'海宁'}

export function MapView({route,points,standalone=false,onWindow}:{route:string;points:Fix[];standalone?:boolean;onWindow:()=>void}){
  const container=useRef<HTMLDivElement>(null), map=useRef<L.Map|null>(null)
  const plan=useRef<L.Polyline|null>(null), trail=useRef<L.Polyline|null>(null), marker=useRef<L.CircleMarker|null>(null), base=useRef<L.LayerGroup|null>(null), online=useRef<L.TileLayer|null>(null), bounds=useRef<L.LatLngBounds|null>(null)
  const [follow,setFollow]=useState(false),[expanded,setExpanded]=useState(false),[onlineBase,setOnlineBase]=useState(false),[mapError,setMapError]=useState('')
  const latest=useRef(points);latest.current=points
  useEffect(()=>{
    if(!container.current)return
    const instance=L.map(container.current,{zoomControl:false,attributionControl:true}).setView([30.3077,120.0785],17)
    instance.attributionControl.setPrefix(false)
    instance.attributionControl.addAttribution('<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>')
    L.control.zoom({position:'bottomright'}).addTo(instance)
    instance.createPane('campus').style.zIndex='250'
    base.current=L.layerGroup().addTo(instance)
    plan.current=L.polyline([],{color:'#8f9da8',weight:3,dashArray:'5 6',opacity:.9}).addTo(instance)
    trail.current=L.polyline([],{color:'#efb457',weight:5,opacity:1}).addTo(instance)
    marker.current=L.circleMarker([30.3077,120.0785],{radius:7,color:'#fff6e5',weight:3,fillColor:'#efb457',fillOpacity:1}).addTo(instance)
    map.current=instance
    const observer=new ResizeObserver(()=>instance.invalidateSize());observer.observe(container.current)
    return()=>{observer.disconnect();instance.remove();map.current=null}
  },[])
  useEffect(()=>{
    let active=true
    setMapError('')
    base.current?.clearLayers()
    api.route(route).then(data=>{
      if(!active||!map.current)return
      plan.current?.setLatLngs(data.coordinates)
      bounds.current=L.latLngBounds(data.coordinates)
      map.current.fitBounds(bounds.current,{padding:[55,55],maxZoom:18,animate:false})
      if(!latest.current.length&&data.coordinates.length)marker.current?.setLatLng(data.coordinates[0])
    }).catch(error=>active&&setMapError(String(error.message)))
    fetch(`/maps/${mapFiles[route]||'zjg'}.geojson`).then(response=>{if(!response.ok)throw Error('校园底图暂不可用');return response.json()}).then(data=>{
      if(!active||!base.current)return
      L.geoJSON(data,{pane:'campus',style:feature=>{
        const kind=feature?.properties.kind,value=feature?.properties.value
        if(kind==='building')return{color:'#35424b',weight:1,fillColor:'#2b3942',fillOpacity:1}
        if(kind==='natural')return{color:'#244450',weight:1,fillColor:'#203d49',fillOpacity:1}
        if(kind==='waterway')return{color:'#244450',weight:3}
        if(kind==='leisure')return{color:'#344b40',weight:1,fillColor:'#294338',fillOpacity:.9}
        return{color:['footway','path','steps'].includes(value)?'#435a5b':'#586c70',weight:['footway','path','steps'].includes(value)?2:5,opacity:.9}
      },onEachFeature:(feature,layer)=>{if(feature.properties.name){const label=document.createElement('span');label.textContent=feature.properties.name;layer.bindTooltip(label,{sticky:true,direction:'top'})}}}).addTo(base.current)
    }).catch(error=>active&&setMapError(error.message))
    return()=>{active=false}
  },[route])
  useEffect(()=>{
    const positions=points.map(point=>[point.latitude,point.longitude] as [number,number])
    trail.current?.setLatLngs(positions)
    if(positions.length){const last=positions[positions.length-1];marker.current?.setLatLng(last);if(follow)map.current?.panTo(last,{animate:true,duration:.4})}
  },[points,follow])
  useEffect(()=>{
    if(!map.current)return
    if(onlineBase){online.current=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map.current);base.current?.remove()}
    else{online.current?.remove();online.current=null;base.current?.addTo(map.current)}
  },[onlineBase])
  function toggleExpanded(){setExpanded(!expanded);setTimeout(()=>map.current?.invalidateSize(),180)}
  return <section className={`map-section ${expanded?'map-expanded':''} ${standalone?'standalone-map':''}`} aria-label="实时路径地图">
    <div className="map-topbar"><div><h2>实时跑步路径</h2><p>{routeNames[route]||'已选路线'} · 已成功发送的位置</p></div><div className="map-actions"><button className="icon-button" title="查看完整路线" aria-label="查看完整路线" onClick={()=>bounds.current&&map.current?.fitBounds(bounds.current,{padding:[55,55]})}><LocateFixed size={17}/></button><button className="icon-button" aria-label={expanded?'还原地图':'展开地图'} onClick={toggleExpanded}>{expanded?<Shrink size={17}/>:<Expand size={17}/>}</button>{!standalone&&<button className="icon-button" aria-label="独立路径窗口" title="独立路径窗口" onClick={onWindow}><ExternalLink size={17}/></button>}</div></div>
    <div className="map-canvas" ref={container} data-testid="live-map"/>
    {mapError&&<div className="map-notice">{mapError}，路线和实时轨迹仍可显示。</div>}
    <div className="map-legend"><span><i className="legend-line planned"/>计划路线</span><span><i className="legend-line"/>已走轨迹</span><span><i className="legend-dot"/>当前位置</span><label className="follow-control"><input type="checkbox" checked={follow} onChange={event=>setFollow(event.target.checked)}/><Crosshair size={14}/>跟随位置</label><button className="quiet-button" onClick={()=>setOnlineBase(!onlineBase)}><MapIcon size={14}/>{onlineBase?'在线底图':'校园底图'}</button></div>
  </section>
}

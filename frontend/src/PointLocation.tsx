import { useEffect, useRef, useState, type FormEvent } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { ClipboardCheck, MapPin, Play, Search, Square } from 'lucide-react'
import { api, type GeoPoint, type Place, type Snapshot } from './api'

const WORLD: [number, number] = [22, 12]

function WorldMap({ point, focus, onChoose }: {
  point: GeoPoint | null
  focus: GeoPoint | null
  onChoose: (point: GeoPoint) => void
}) {
  const canvas = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const marker = useRef<L.CircleMarker | null>(null)
  const choose = useRef(onChoose)
  choose.current = onChoose
  const [mapLoading, setMapLoading] = useState(true)
  const [mapError, setMapError] = useState(false)

  useEffect(() => {
    if (!canvas.current) return
    const view = L.map(canvas.current, { zoomControl: false, worldCopyJump: true, minZoom: 1 })
      .setView(WORLD, 2)
    map.current = view
    view.attributionControl.setPrefix(false)
    L.control.zoom({ position: 'bottomright' }).addTo(view)
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">© OpenStreetMap contributors</a>',
    })
    tiles.on('loading', () => {
      setMapLoading(true)
      setMapError(false)
    })
    tiles.on('load', () => setMapLoading(false))
    tiles.on('tileerror', () => setMapError(true))
    tiles.addTo(view)
    view.on('click', (event: L.LeafletMouseEvent) => {
      const point = event.latlng.wrap()
      choose.current({ latitude: point.lat, longitude: point.lng })
    })
    const resize = new ResizeObserver(() => view.invalidateSize())
    resize.observe(canvas.current)
    return () => {
      resize.disconnect()
      view.remove()
      marker.current = null
      map.current = null
    }
  }, [])

  useEffect(() => {
    if (!map.current || !point) return
    const position: [number, number] = [point.latitude, point.longitude]
    if (!marker.current) {
      marker.current = L.circleMarker(position, {
        radius: 8, color: '#fff5df', weight: 3, fillColor: '#efb457', fillOpacity: 1, interactive: false,
      }).addTo(map.current)
    } else {
      marker.current.setLatLng(position)
    }
  }, [point])

  useEffect(() => {
    if (!map.current || !focus) return
    const animate = !window.matchMedia('(prefers-reduced-motion: reduce)').matches
    map.current.setView([focus.latitude, focus.longitude], 15, { animate })
  }, [focus])

  return <div className="point-map">
    <div className="point-map-canvas" ref={canvas} data-testid="world-map" aria-label="世界地图" />
    {(mapError || mapLoading) && <p className="point-map-warning" role="status">
      {mapError ? '部分地图暂时不可用，可以继续搜索地点或输入坐标。' : '正在加载地图…'}
    </p>}
  </div>
}

type PointLocationProps = {
  backend: string
  snapshot: Snapshot
  disabled: boolean
  onBackend: (name: string) => void
  onAction: (action: string, values?: Record<string, unknown>) => Promise<void>
}

export function PointLocation({ backend, snapshot, disabled, onBackend, onAction }: PointLocationProps) {
  const session = snapshot.point
  const holding = session.status === 'starting' || session.status === 'active'
  const [target, setTarget] = useState<GeoPoint | null>(session.target)
  const [focus, setFocus] = useState<GeoPoint | null>(session.target)
  const [query, setQuery] = useState('')
  const [places, setPlaces] = useState<Place[]>([])
  const [searched, setSearched] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState('')
  const queued = useRef<GeoPoint | null>(null)
  const moving = useRef(false)
  const applied = session.applied
  const confirmed = holding && applied && target?.latitude === applied.latitude && target?.longitude === applied.longitude

  async function choose(point: GeoPoint) {
    setTarget(point)
    if (!holding || snapshot.stopping) return
    queued.current = point
    if (moving.current) return
    moving.current = true
    try {
      while (queued.current) {
        const active = queued.current
        queued.current = null
        await onAction('point_move', { ...active })
      }
    } finally {
      moving.current = false
    }
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!query.trim() || searching) return
    setSearching(true)
    setSearchError('')
    setPlaces([])
    try {
      setPlaces((await api.search(query.trim())).places)
      setSearched(true)
    } catch (error) {
      setSearchError((error as Error).message)
    } finally {
      setSearching(false)
    }
  }

  function pickResult(place: Place) {
    setFocus(place)
    setPlaces([])
    setSearched(false)
    void choose(place)
  }

  function stop() {
    queued.current = null
    void onAction('stop')
  }

  return <section className="point-workspace" aria-label="定点定位">
    <aside className="point-inspector">
      <div className="point-heading">
        <h1>定点定位</h1>
        <p>点击地图选点，或搜索全球地点。</p>
      </div>
      <div className="field">
        <label htmlFor="point-backend">设备</label>
        <div className="point-device">
          <select id="point-backend" value={backend} disabled={disabled || snapshot.busy} onChange={event => onBackend(event.target.value)}>
            <option value="ios">iPhone / iPad</option>
            <option value="android">Android 模拟器</option>
          </select>
          <button className="button" title="检查设备" aria-label="检查设备" disabled={disabled || snapshot.busy} onClick={() => onAction('check')}><ClipboardCheck size={17} /></button>
        </div>
      </div>
      <form className="point-search" role="search" onSubmit={search}>
        <label htmlFor="point-search">搜索地点</label>
        <div className="point-search-row">
          <input id="point-search" type="search" maxLength={160} value={query} placeholder="城市、地址或纬度, 经度" onChange={event => setQuery(event.target.value)} />
          <button className="button" aria-label="搜索" title="搜索" disabled={searching || !query.trim()}><Search size={17} /></button>
        </div>
        <span className="field-hint">在线搜索由 <a href="https://github.com/komoot/photon" target="_blank" rel="noopener noreferrer">Photon</a> 提供。</span>
        {searching && <p role="status">正在搜索…</p>}
        {searchError && <p role="alert">{searchError}</p>}
        {searched && !searching && !searchError && !places.length && <p role="status">未找到地点，试试更完整的地址。</p>}
        {!!places.length && <ul className="point-results" aria-label="搜索结果">
          {places.map((place, index) => <li key={place.label + index}><button type="button" onClick={() => pickResult(place)}><MapPin size={15} /><span>{place.label}</span></button></li>)}
        </ul>}
      </form>
      <div className="point-selection">
        <div className="point-status" role="status" data-testid="point-status">
          {snapshot.stopping && holding ? '正在停止' : confirmed ? '定点定位中' : holding ? '正在设置位置' : target ? '已选位置' : '尚未选点'}
        </div>
        {target && <output className="point-coordinates">{target.latitude.toFixed(6)}, {target.longitude.toFixed(6)}</output>}
        {holding ? <button className="button danger" disabled={snapshot.stopping} onClick={stop}><Square size={15} />停止定位</button> :
          <button className="button primary" disabled={disabled || snapshot.busy || !target} onClick={() => target && onAction('point_start', { ...target })}><Play size={16} />开始定点定位</button>}
        {confirmed && <span className="field-hint">继续点选地图即可切换位置。</span>}
      </div>
    </aside>
    <WorldMap point={target} focus={focus} onChoose={choose} />
  </section>
}

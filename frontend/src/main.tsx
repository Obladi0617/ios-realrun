import React, { useCallback, useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Activity, ArrowDownToLine, ArrowRight, Check, CheckCheck, CircleHelp, ClipboardCheck, Clock3, Download, Gauge, HardDrive, LoaderCircle, MapPinned, Play, RefreshCw, Route, Settings2, ShieldCheck, Smartphone, Square, Terminal, X } from 'lucide-react'
import { api, type Fix, type Settings, type Snapshot } from './api'
import { MapView } from './MapView'
import './style.css'

const names:Record<string,string>={
  'ZJGroute.txt':'紫金港 · 默认路线',
  'ZJGWestTrack.geojson':'紫金港 · 西田径场（400 米）',
  'YQroute.txt':'玉泉 · 默认路线',
  'HNroute.txt':'海宁 · 默认路线',
}
const apps={tyys:{name:'浙大体艺',monogram:'体艺',description:'在官方 App 中完成首次协议和浙大统一身份认证。'},ding:{name:'钉钉',monogram:'钉钉',description:'使用钉钉提供的登录方式，再选择浙江大学组织。'}}
function timeLabel(seconds:number){const value=Math.floor(seconds*10);return `${String(Math.floor(value/600)).padStart(2,'0')}:${String(Math.floor(value/10)%60).padStart(2,'0')}.${value%10}`}
function paceLabel(speed:number){if(!Number.isFinite(speed)||speed<.1)return '—';const seconds=Math.round(1000/speed);return `${Math.floor(seconds/60)}′${String(seconds%60).padStart(2,'0')}″`}
const initialParams=new URLSearchParams(location.search)

function App(){
  const [page,setPage]=useState<'workbench'|'apps'|'settings'>('workbench'),[snapshot,setSnapshot]=useState<Snapshot|null>(null),[settings,setSettings]=useState<Settings|null>(null)
  const [points,setPoints]=useState<Fix[]>([]),[logs,setLogs]=useState<Snapshot['logs']>([]),[error,setError]=useState(''),[connected,setConnected]=useState(false),[showLogs,setShowLogs]=useState(false),[saved,setSaved]=useState(false),[sending,setSending]=useState(false)
  const polling=useRef({cursor:0,run:'',logs:0}),dirty=useRef(false),mounted=useRef(true),lastSettings=useRef('')
  const standalone=initialParams.get('view')==='map'
  useEffect(()=>{mounted.current=true;let cancelled=false,timer:number;async function poll(){
    try{const state=await api.state(polling.current.cursor,polling.current.run,polling.current.logs);if(cancelled)return
      setSnapshot(state);setConnected(true)
      const key=JSON.stringify(state.settings)
      if(!dirty.current&&key!==lastSettings.current){setSettings(state.settings);lastSettings.current=key}
      setPoints(previous=>{let result=state.run.reset?state.run.points:state.run.points.length?[...previous,...state.run.points]:previous;while(result.length>12000)result=result.filter((_,index)=>index%2===0);return result})
      if(state.logs.length)setLogs(previous=>[...previous,...state.logs].slice(-300))
      polling.current={cursor:state.run.cursor,run:state.run.id,logs:state.logCursor}
    }catch(caught){if(!cancelled){setConnected(false);setError((caught as Error).message)}}
    if(!cancelled)timer=window.setTimeout(poll,500)
  }poll();return()=>{cancelled=true;mounted.current=false;clearTimeout(timer)}},[])
  function edit(key:keyof Settings,value:string){dirty.current=true;setSaved(false);setSettings(previous=>previous?{...previous,[key]:value}:previous)}
  const save=useCallback(async()=>{if(!settings)return;await api.save(settings);dirty.current=false;lastSettings.current=JSON.stringify(settings);setSaved(true)},[settings])
  async function action(name:string,values:Record<string,unknown>={}){
    setError('');setSending(true)
    try{if(dirty.current&&name!=='stop'&&name!=='phone_hide')await save();await api.action(name,values)}catch(caught){setError((caught as Error).message)}finally{if(mounted.current)setSending(false)}
  }
  async function saveOnly(){setError('');try{await save()}catch(caught){setError((caught as Error).message)}}
  if(!snapshot||!settings)return <div className="loading"><Route size={25}/><span>正在连接本机工作台…</span>{error&&<p role="alert">{error}</p>}</div>
  const busy=snapshot.busy||sending,android=settings.backend==='android',running=['running','starting'].includes(snapshot.run.status)&&snapshot.busy
  const selected=(settings.app in apps?settings.app:'tyys') as keyof typeof apps
  const liveRoute=running&&snapshot.run.route?snapshot.run.route:settings.route
  const last=points.at(-1),stale=running&&snapshot.run.lastFixAt&&Date.now()/1000-snapshot.run.lastFixAt>3
  const update=snapshot.update
  const status=!connected?'连接中断':stale?'位置更新中断':snapshot.stopping?'正在停止':running?'正在定位':snapshot.task.status==='error'?'操作失败':snapshot.device.status==='ready'?'设备已就绪':'等待设备'
  const phoneButton=<button className="button" disabled={sending||!android} onClick={()=>action(snapshot.phone.status==='open'?'phone_hide':'phone_show')}><Smartphone size={16}/>{snapshot.phone.status==='open'?'收起手机':'显示手机'}</button>
  return <div className={`app-shell ${standalone?'map-only':''}`} data-connected={connected} data-point-count={snapshot.run.pointCount} data-run-id={snapshot.run.id}>
    {!standalone&&<header className="app-header"><div className="brand"><Route size={23}/><strong>RealRun</strong><span>v{snapshot.version}</span></div><nav aria-label="主导航">{([{key:'workbench',label:'工作台',icon:MapPinned},{key:'apps',label:'应用',icon:Smartphone},{key:'settings',label:'设置',icon:Settings2}] as const).map(item=><button key={item.key} className={page===item.key?'active':''} onClick={()=>setPage(item.key)}><item.icon size={16}/>{item.label}</button>)}</nav><div className="header-state"><i className={`status-dot ${!connected||snapshot.task.status==='error'?'warning':''}`}/>{status}</div></header>}
    {error&&<div className="error-banner" role="alert"><CircleHelp size={17}/><span>{error}</span><button aria-label="关闭提示" onClick={()=>setError('')}><X size={16}/></button></div>}
    {!connected&&snapshot&&<div className="connection-banner">与本机服务的连接已中断，正在重新连接；当前显示的是最后收到的位置。</div>}
    {stale&&<div className="connection-banner">已经超过 3 秒没有收到新位置，轨迹保持在最后一个已确认坐标。</div>}
    {(standalone||page==='workbench')&&<div className="workspace">
      {!standalone&&<aside className="run-sidebar">
        <div className="field"><label>设备类型</label><div className="segmented"><button disabled={busy} className={android?'active':''} onClick={()=>edit('backend','android')}>Android</button><button disabled={busy} className={!android?'active':''} onClick={()=>edit('backend','ios')}>iPhone</button></div></div>
        {android&&<div className="field"><label htmlFor="work-app">当前应用</label><select id="work-app" disabled={busy} value={selected} onChange={event=>edit('app',event.target.value)}><option value="tyys">浙大体艺</option><option value="ding">钉钉</option></select><span className="field-hint">{snapshot.apps[selected].confirmedAt?'上次登录已由你确认':'登录状态待确认'}</span></div>}
        <div className="field"><label htmlFor="work-route">路线</label><select id="work-route" disabled={busy} value={settings.route} onChange={event=>edit('route',event.target.value)}>{Object.entries(names).map(([key,name])=><option key={key} value={key}>{name}</option>)}</select></div>
        <div className="field"><label htmlFor="work-speed">目标速度 <span>m/s</span></label><input id="work-speed" disabled={busy} type="number" min="0.1" max="100" step="any" value={settings.speed} onChange={event=>edit('speed',event.target.value)}/><span className="field-hint" data-testid="target-pace">对应 {paceLabel(Number(settings.speed))}/km · {(Number(settings.speed)*3.6).toFixed(2)} km/h</span></div>
        <div className="field"><label htmlFor="work-minutes">运行时长 <span>分钟</span></label><input id="work-minutes" disabled={busy} type="number" min="0" value={settings.minutes} onChange={event=>edit('minutes',event.target.value)}/><span className="field-hint">0 表示按目标里程停止</span></div>
        <div className="field"><label htmlFor="work-profile">配速波动</label><select id="work-profile" disabled={busy} value={settings.profile} onChange={event=>edit('profile',event.target.value)}><option value="constant">匀速</option><option value="steady">平稳</option><option value="recreational">业余跑者</option><option value="variable">波动较大</option></select><span className="field-hint">匀速保持目标速度，其他档位会随过程变化。</span></div>
        <div className="sidebar-actions"><button className="button" disabled={busy} onClick={()=>action('check')}><ClipboardCheck size={15}/>检查设备</button>{!android&&<button className="button" disabled={busy} onClick={()=>action('mount')}>挂载镜像</button>}{android&&phoneButton}</div>
      </aside>}
      <main className="work-main">
        <div className="work-heading"><div><span className="eyebrow">{android?'本机虚拟手机':'USB 设备'}</span><h1>{android?'路线工作台':'iPhone 路线工作台'}</h1></div>{!standalone&&<div className="run-controls">{running||snapshot.stopping?<button className="button danger" disabled={snapshot.stopping} onClick={()=>action('stop')}><Square size={15}/>{snapshot.stopping?'正在停止':'停止定位'}</button>:<button className="button primary" data-testid="start-run" disabled={busy||!connected} onClick={()=>action('run')}><Play size={16}/>开始定位</button>}{busy&&!running&&!snapshot.stopping&&<button className="button" onClick={()=>action('stop')}>取消任务</button>}</div>}</div>
        <div className="run-metrics"><div><span><Route size={14}/>已行进</span><strong data-testid="run-distance" data-metres={snapshot.run.distance}>{snapshot.run.distance<1000?snapshot.run.distance.toFixed(1):(snapshot.run.distance/1000).toFixed(3)}<small>{snapshot.run.distance<1000?'m':'km'}</small></strong></div><div><span><Gauge size={14}/>即时配速</span><strong data-testid="instant-pace" data-speed={snapshot.run.speed}>{paceLabel(snapshot.run.speed)}<small>/km</small></strong><em className="metric-caption" data-testid="instant-speed">{snapshot.run.speed.toFixed(2)} m/s</em></div><div><span><Clock3 size={14}/>用时</span><strong data-testid="run-elapsed" data-seconds={snapshot.run.elapsed}>{timeLabel(snapshot.run.elapsed)}</strong></div><div className="metric-average"><span><Gauge size={14}/>平均配速</span><strong data-testid="average-pace">{paceLabel(snapshot.run.elapsed>0?snapshot.run.distance/snapshot.run.elapsed:0)}<small>/km</small></strong><em className="metric-caption">全程里程 / 用时</em></div></div>
        <MapView route={liveRoute} points={snapshot.run.route===liveRoute?points:[]} standalone={standalone} onWindow={()=>action('map_window')}/>
        <div className="run-detail"><span>{last?`${last.latitude.toFixed(6)}, ${last.longitude.toFixed(6)}`:'等待第一个位置'}</span><span data-testid="fix-count">{snapshot.run.pointCount} 次位置更新</span><span>{snapshot.run.status==='stopped'?'坐标推送已停止，轨迹已保留':running?'按已确认发送的位置更新':'轨迹仅在定位任务运行时更新'}</span></div>
      </main>
    </div>}
    {!standalone&&page==='apps'&&<main className="page-content apps-page"><div className="page-heading"><div><span className="eyebrow">固定虚拟手机 · 保留应用数据</span><h1>应用与登录</h1><p>在官方 App 中完成登录，后续打开同一台虚拟手机继续使用。</p></div><button className="button" disabled={busy} onClick={()=>action('check')}><RefreshCw size={15}/>刷新应用</button></div>
      <div className="app-list">{Object.entries(apps).map(([key,app])=>{const info=snapshot.apps[key];return <section className="app-entry" key={key}><div className="app-avatar">{app.monogram}</div><div className="app-info"><h2>{app.name}</h2><div className="app-metadata">{info.installed===null?'等待检查':info.installed?`已安装 · ${info.version}`:'尚未安装'}<span>·</span>{info.confirmedAt?'上次登录已由你确认':'首次登录待确认'}</div><p>{app.description}</p><div className="app-inline-actions"><button className="text-button" disabled={busy} onClick={()=>action('confirm_login',{app:key})}><CheckCheck size={14}/>我已完成登录</button>{info.confirmedAt&&<button className="text-button" disabled={busy} onClick={()=>action('confirm_login',{app:key,confirmed:false})}>清除确认状态</button>}<button className="text-button" disabled={busy} onClick={()=>action('update_app',{app:key})}><ArrowDownToLine size={14}/>安装官方最新版</button></div></div><button className="button primary" disabled={busy||!android} onClick={()=>action('open_app',{app:key})}>{info.installed?'打开 / 登录':'安装并打开'}<ArrowRight size={15}/></button></section>})}</div>
      {!android&&<div className="inline-note">应用管理使用 Android 虚拟手机，请在工作台切换到 Android 模式。</div>}
      <div className="apps-bottom"><div><ShieldCheck size={19}/><div><strong>账号信息在官方页面中输入</strong><p>本软件只保存设备与路线设置，以及你确认登录的时间。</p></div></div><button className="button" disabled={busy||!android} onClick={()=>action('install_apk')}><Download size={15}/>安装本机 APK</button></div>
      <div className="session-note"><HardDrive size={16}/>收起手机窗口不关闭虚拟设备。重新登录通常不需要重建虚拟手机。</div>
    </main>}
    {!standalone&&page==='settings'&&<main className="page-content settings-page"><div className="page-heading"><div><span className="eyebrow">本机设置</span><h1>设置</h1><p>设置保存在安装目录之外，程序更新后继续使用。</p></div><button className="button primary" disabled={busy} onClick={saveOnly}>{saved?<Check size={16}/>:<Settings2 size={16}/>}保存设置</button></div>
      <section className="settings-section"><div><h2>Android 环境</h2><p>留空时自动查找 SDK，使用固定虚拟设备保留 App 数据。</p></div><div className="settings-fields">{([{key:'sdk',label:'Android SDK',placeholder:'D:\\Android\\Sdk'},{key:'avd',label:'虚拟设备名称',placeholder:'RealRun_Android15'},{key:'serial',label:'设备编号',placeholder:'留空选择对应的虚拟设备'},{key:'android_home',label:'虚拟手机数据目录',placeholder:'默认 SDK 旁的 RealRunTest 英文目录'},{key:'scrcpy',label:'手机窗口工具（可选）',placeholder:'留空自动下载并校验官方 scrcpy'}] as const).map(item=><div className="field" key={item.key}><label htmlFor={`setting-${item.key}`}>{item.label}</label><input id={`setting-${item.key}`} disabled={busy} value={settings[item.key]} placeholder={item.placeholder} onChange={event=>edit(item.key,event.target.value)}/></div>)}<div className="inline-note">需要 Android SDK 的 emulator、platform-tools 和 Android 15 Google APIs x86_64 镜像。首次创建虚拟设备还需要 cmdline-tools 和 JDK。</div><button className="button" disabled={busy} onClick={()=>action('prepare_phone')}><Smartphone size={15}/>准备手机窗口工具</button></div></section>
      <section className="settings-section"><div><h2>程序更新</h2><p>从本项目 GitHub Releases 获取正式安装包，下载后校验 SHA256。</p></div><div className="update-settings"><div className="update-version"><span>当前版本</span><strong>v{snapshot.version}</strong></div>{update.status==='latest'&&<span className="success-text"><Check size={15}/>当前已是最新版本</span>}{['available','ready'].includes(update.status)&&<p>发现新版本 v{update.version}</p>}<div className="button-row"><button className="button" disabled={busy} onClick={()=>action('check_update')}><RefreshCw size={15}/>检查更新</button>{update.status==='available'&&<button className="button primary" disabled={busy} onClick={()=>action('download_update')}>下载新版本</button>}{update.status==='ready'&&<button className="button primary" disabled={busy} onClick={()=>action('install_update')}>退出并安装</button>}</div></div></section>
      <section className="settings-section"><div><h2>虚拟手机性能</h2><p>根据电脑可用资源分配内存与核心数，控制画面传输开销。</p></div><div className="settings-fields"><div className="field"><label htmlFor="setting-android_gpu">图形加速</label><select id="setting-android_gpu" disabled={busy} value={settings.android_gpu} onChange={event=>edit('android_gpu',event.target.value)}><option value="auto">自动选择（推荐）</option><option value="host">使用电脑显卡</option><option value="swiftshader">软件兼容模式</option></select></div><p className="inline-note">显卡初始化失败时自动尝试兼容模式。修改后重启虚拟手机以应用设置，保留已有 App 与登录数据。</p><button className="button" disabled={busy||!android} onClick={()=>action('restart_phone')}><RefreshCw size={15}/>重启虚拟手机</button></div></section>
      <section className="settings-section"><div><h2>设备数据</h2><p>登录状态由各 App 自己保存在虚拟手机内。</p></div><div className="settings-copy"><p>程序升级、收起手机窗口和停止路线均不会清除 App 数据。</p><p>更换虚拟设备目录或重建 AVD 后，需要在对应 App 中重新登录。</p></div></section>
    </main>}
    {!standalone&&<footer className="status-footer"><div className="task-status">{snapshot.busy?<LoaderCircle size={14} className="spin"/>:snapshot.task.status==='success'?<Check size={14}/>:<Activity size={14}/>}<span title={snapshot.task.label}>{snapshot.task.label}</span></div><span className="status-device">{snapshot.device.serial||snapshot.device.label}</span><button className="quiet-button" onClick={()=>setShowLogs(!showLogs)}><Terminal size={14}/>{showLogs?'收起日志':'运行日志'}</button></footer>}
    {showLogs&&<section className="log-drawer"><div><strong>运行日志</strong><button className="icon-button" aria-label="关闭日志" onClick={()=>setShowLogs(false)}><X size={16}/></button></div><pre>{logs.map(line=>`${line.time}  ${line.text}`).join('\n')}</pre></section>}
  </div>
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App/></React.StrictMode>)

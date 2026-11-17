// Opt-in CLI verification against the explicitly named disposable Android AVD.
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { chromium } from 'playwright-core'

const execute=promisify(execFile)
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..')
const args=Object.fromEntries(process.argv.slice(2).reduce((pairs,item,index,array)=>item.startsWith('--')?[...pairs,[item.slice(2),array[index+1]]]:pairs,[]))
if(!args.connection||!args.sdk||!args.avd)throw Error('Supply --connection, --sdk and --avd')
const connection=JSON.parse(await fs.readFile(args.connection,'utf8'))
const api=async(endpoint,body)=>{
  const response=await fetch(connection.origin+endpoint,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+connection.token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)})
  const result=await response.json();if(!response.ok)throw Error(result.error);return result
}
async function idle(){for(let index=0;index<300;index++){const state=await api('/api/state');if(!state.busy){if(state.task.status==='error')throw Error(state.task.label);return state}await new Promise(resolve=>setTimeout(resolve,100))}throw Error('Desktop task did not finish')}
const adb=path.join(args.sdk,'platform-tools','adb.exe')
const serial=args.serial||'emulator-5554'
async function command(...parameters){return (await execute(adb,['-s',serial,...parameters],{windowsHide:true,timeout:30000,maxBuffer:4*1024*1024})).stdout}
const avd=(await command('emu','avd','name')).split(/\r?\n/)[0].trim()
if(avd!==args.avd)throw Error('Refusing to operate on a different AVD')
await api('/api/settings',{backend:'android',sdk:args.sdk,serial,avd:args.avd,android_home:args.home||path.dirname(path.dirname(args.sdk))+'/Android/RealRunTest',route:'ZJGroute.txt',speed:'4.8',minutes:'1',profile:'constant'})
await api('/api/action',{action:'check'})
const checked=await idle()
if(!checked.apps.tyys.installed)throw Error('The official TYYS APK must be installed before this smoke check')
const browser=await chromium.launch({executablePath:args.chrome||'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true,args:['--no-proxy-server','--disable-gpu']})
const errors=[]
const context=await browser.newContext({viewport:{width:1280,height:950}})
const page=await context.newPage()
page.on('pageerror',error=>errors.push(error.message))
let probePid='',result
try{
  await command('shell','pm','grant','local.realrun.gpsprobe','android.permission.ACCESS_COARSE_LOCATION')
  await command('shell','pm','grant','local.realrun.gpsprobe','android.permission.ACCESS_FINE_LOCATION')
  await command('shell','am','start','-S','-W','-n','local.realrun.gpsprobe/.GpsProbe')
  probePid=(await command('shell','pidof','local.realrun.gpsprobe')).trim().split(/\s+/)[0]
  await page.goto(connection.url)
  await page.getByRole('heading',{name:'路线工作台',exact:true}).waitFor()
  await page.waitForFunction(()=>document.querySelectorAll('.leaflet-campus-pane path').length>30)
  await page.getByRole('button',{name:'应用',exact:true}).click()
  await page.locator('.app-metadata').filter({hasText:'已安装 · 2.9.7'}).waitFor()
  await page.getByRole('button',{name:'设置',exact:true}).click()
  await page.locator('#setting-sdk').waitFor()
  if(await page.locator('#setting-android_gpu option').count()!==3)throw Error('Missing portable graphics modes')
  await page.getByRole('button',{name:'重启虚拟手机',exact:true}).waitFor()
  if((await page.locator('#setting-sdk').inputValue())!==args.sdk)throw Error('Saved SDK selection did not reach the UI')
  await page.getByRole('button',{name:'工作台',exact:true}).click()
  if(!(await page.getByTestId('target-pace').textContent()).includes('3′28″/km'))throw Error('Target pace unit conversion is incorrect')
  const mapPage=await context.newPage()
  mapPage.on('pageerror',error=>errors.push(error.message))
  await mapPage.goto(connection.origin+'/?view=map#token='+connection.token)
  await mapPage.getByRole('heading',{name:'实时跑步路径',exact:true}).waitFor()
  const previousRun=(await api('/api/state')).run.id
  await page.getByTestId('start-run').click()
  await page.waitForFunction(previous=>{const root=document.querySelector('.app-shell');return root?.dataset.runId!==previous&&Number(root?.dataset.pointCount)>=10},previousRun,{timeout:30000})
  await mapPage.waitForFunction(previous=>{const root=document.querySelector('.app-shell');return root?.dataset.runId!==previous&&Number(root?.dataset.pointCount)>=10},previousRun,{timeout:30000})
  const during=await api('/api/state')
  await page.waitForTimeout(2000)
  const moved=await api('/api/state')
  if(moved.run.cursor<=during.run.cursor||moved.run.distance<=during.run.distance)throw Error('Live worker coordinates did not advance')
  const visible=await page.evaluate(()=>({speed:Number(document.querySelector('[data-testid="instant-pace"]')?.getAttribute('data-speed')),distance:Number(document.querySelector('[data-testid="run-distance"]')?.getAttribute('data-metres')),elapsed:Number(document.querySelector('[data-testid="run-elapsed"]')?.getAttribute('data-seconds')),instant:document.querySelector('[data-testid="instant-pace"]')?.textContent,average:document.querySelector('[data-testid="average-pace"]')?.textContent}))
  const paceSeconds=text=>{const match=text?.match(/(\d+)′(\d+)″/);if(!match)throw Error('A pace value is missing');return Number(match[1])*60+Number(match[2])}
  if(Math.abs(paceSeconds(visible.instant)-1000/visible.speed)>.51)throw Error('Instantaneous pace does not match displayed speed')
  if(Math.abs(paceSeconds(visible.average)-1000*visible.elapsed/visible.distance)>.51)throw Error('Average pace does not match distance and elapsed time')
  await page.screenshot({path:path.join(root,'build/desktop-live-workbench.png'),fullPage:true})
  await mapPage.screenshot({path:path.join(root,'build/desktop-live-map-window.png'),fullPage:true})
  await page.getByRole('button',{name:'停止定位',exact:true}).click()
  const stopped=await idle()
  await page.waitForTimeout(1000)
  const after=await api('/api/state')
  if(stopped.run.cursor!==after.run.cursor||after.run.status!=='stopped')throw Error('Stopping did not freeze the last confirmed position')
  if(after.run.speed!==0)throw Error('Stopping left a stale instantaneous speed')
  const raw=await command('logcat','-d','--pid='+probePid,'-v','raw','-s','RealRunGPSProbe:I','*:S')
  const fixes=raw.split(/\r?\n/).filter(line=>line.startsWith('{')).map(line=>JSON.parse(line))
  if(new Set(fixes.map(point=>point.latitude+','+point.longitude)).size<2)throw Error('Android app did not observe moving GPS fixes')
  await page.setViewportSize({width:720,height:1000})
  await page.waitForTimeout(250)
  if(!await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth))throw Error('The UI overflows a narrow viewport')
  if(errors.length)throw Error(errors.join('; '))
  result={version:after.version,avd,frontend_page_errors:errors.length,offline_map_features:await page.locator('.leaflet-campus-pane path').count(),tyys_version:checked.apps.tyys.version,dingtalk_version:checked.apps.ding.version,live_fix_count:after.run.pointCount,distance_metres:after.run.distance,gps_callbacks:fixes.length,coordinates_changed:true,two_map_pages_synchronized:true,stop_froze_position:true,pace_matches_speed_and_distance:true,narrow_layout_no_horizontal_overflow:true,route_status:after.run.status}
  await fs.writeFile(path.join(root,'build/desktop-live-verification.json'),JSON.stringify(result,null,2))
  console.log(JSON.stringify(result,null,2))
}finally{
  await api('/api/action',{action:'stop'}).catch(()=>{})
  await command('shell','am','force-stop','local.realrun.gpsprobe').catch(()=>{})
  await browser.close()
}

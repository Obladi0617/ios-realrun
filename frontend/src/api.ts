export type Settings = {backend:string;route:string;speed:string;minutes:string;profile:string;sdk:string;serial:string;avd:string;app:string;android_home:string;android_gpu:string;scrcpy:string;login_tyys:string;login_ding:string}
export type Fix = {sequence:number;latitude:number;longitude:number;distance:number;elapsed:number;speed:number}
export type AppInfo = {name:string;installed:boolean|null;version:string;confirmedAt?:string}
export type Snapshot = {
  version:string; settings:Settings; busy:boolean; stopping:boolean;
  task:{status:string;label:string;action:string};device:{status:string;serial:string;label:string};
  apps:Record<string,AppInfo>;phone:{status:string;error?:string};
  update:{status:string;version?:string;path?:string};
  capabilities?:{nativeWindows:boolean;admin:boolean};
  run:{id:string;status:string;cursor:number;reset:boolean;points:Fix[];pointCount:number;distance:number;elapsed:number;speed:number;reason:string;route?:string;lastFixAt?:number};
  logs:{id:number;text:string;time:string}[];logCursor:number
}
const fragment = new URLSearchParams(location.hash.slice(1))
const token = fragment.get('token') || ''

async function request<T>(path:string,body?:unknown):Promise<T>{
  const response=await fetch(path,{method:body===undefined?'GET':'POST',headers:{Authorization:`Bearer ${token}`,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body)})
  const payload=await response.json()
  if(!response.ok)throw new Error(payload.error||`请求失败 (${response.status})`)
  return payload as T
}
export const api={
  state:(cursor:number,run:string,logs:number)=>request<Snapshot>(`/api/state?cursor=${cursor}&run=${encodeURIComponent(run)}&logs=${logs}`),
  action:(action:string,values:Record<string,unknown>={})=>request<{ok:boolean}>('/api/action',{action,values}),
  save:(settings:Partial<Settings>)=>request<{settings:Settings}>('/api/settings',settings),
  route:(name:string)=>request<{coordinates:[number,number][]}>(`/api/route?name=${encodeURIComponent(name)}`),
}

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname,"inject-pwa.js"),"utf8");
const script = source.match(/<script>([\s\S]*?)<\/script>/)[1];
function run(pathname,controller) {
  let handler, reloads=0;
  vm.runInNewContext(script, {
    navigator:{serviceWorker:{controller,addEventListener:(_event,fn)=>{handler=fn;}}},
    window:{location:{pathname,reload:()=>{reloads++;}},addEventListener(){}},
  });
  return { change:()=>handler(), reloads:()=>reloads };
}
const first=run("/",null); first.change(); assert.equal(first.reloads(),0);
for (const route of ["assessment","exercise","camera-check","session-check","task-intro","emergency"]) {
  const session=run(`/${route}`,{}); session.change(); assert.equal(session.reloads(),0,route);
}
const home=run("/",{}); home.change(); home.change(); assert.equal(home.reloads(),1);
const worker = fs.readFileSync(path.join(__dirname,"../public/sw.js"),"utf8");
const handlers={};
vm.runInNewContext(worker,{self:{location:{origin:"https://rehyn.test"},addEventListener:(name,fn)=>{handlers[name]=fn;},skipWaiting(){}},URL});
let intercepted=false;
handlers.fetch({request:{method:"GET",url:"https://rehyn.test/camera-setup/index.html",mode:"navigate"},respondWith:()=>{intercepted=true;}});
assert.equal(intercepted,false,"camera setup must not replace the cached app shell");
console.log("PWA updates: first installation and active camera sessions are not reloaded; home update reloads once.");

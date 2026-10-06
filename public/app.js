"use strict";
/* Urna do Grêmio - frontend. Todos os dados vêm/vão para a API Flask (/api/...). */

const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const $=id=>document.getElementById(id);

let E=null;            // estado vindo do servidor
let R=null;            // resultado (só mesário)
let view="load",digits="",blank=false,done=false,busy=false;
let err="",msg="",aviso="",confirmReset=false,tab="chapas",editing=null;
let draft={n:"",name:"",img:""},doneTimer=null;

/* ---------- API ---------- */
async function api(path,method="GET",body){
  try{
    const r=await fetch(path,{method,credentials:"same-origin",
      headers:body?{"Content-Type":"application/json"}:{},
      body:body?JSON.stringify(body):undefined});
    const j=await r.json().catch(()=>({}));
    return {...j,ok:r.ok,status:r.status};
  }catch(e){return {ok:false,status:0,erro:"Sem conexão com o servidor."}}
}
async function carregar(){
  E=await api("/api/estado");
  if(!E.ok&&E.status===0){document.getElementById("app").innerHTML=`<div class="card"><h1>Sem conexão</h1><p>Não foi possível falar com o servidor.</p><button class="btn" onclick="carregar()">Tentar de novo</button></div>`;return}
  rota();
}
function rota(){
  err=msg=aviso="";
  if(E.logado)view=E.ativa?"admin":"setup";
  else if(E.urna_liberada&&E.chapas.length)view="vote";
  else view="login";
  render();
}
function render(){
  if(view==="setup")return setup();
  if(view==="login")return login();
  if(view==="admin")return admin();
  return vote();
}

/* ---------- SOM ---------- */
let ac;
function ctx(){
  try{ac=ac||new(window.AudioContext||window.webkitAudioContext)();if(ac.state==="suspended")ac.resume();return ac}catch(e){return null}
}
function tone(freq,start,dur,vol,type){
  const a=ctx();if(!a)return;
  const t=a.currentTime+start,o=a.createOscillator(),g=a.createGain();
  o.type=type||"square";o.frequency.value=freq;
  const at=Math.min(.006,dur/4);
  g.gain.setValueAtTime(0.0001,t);
  g.gain.exponentialRampToValueAtTime(vol||.07,t+at);
  g.gain.setValueAtTime(vol||.07,t+Math.max(dur-.012,at));
  g.gain.exponentialRampToValueAtTime(0.0001,t+dur);
  o.connect(g);g.connect(a.destination);o.start(t);o.stop(t+dur+.02);
}
// 3 beeps de ~130 ms, pausa ~65 ms (ajuste aqui)
const SOM={freq:1900,beeps:3,dur:.13,pausa:.065,vol:.08};
const sTecla=()=>tone(1700,0,.06,.05);
const sCorrige=()=>tone(1300,0,.12,.05);
const sBranco=()=>tone(1700,0,.06,.05);
const sErro=()=>{tone(900,0,.1,.06);tone(900,.16,.1,.06)};
const sConfirma=()=>{for(let i=0;i<SOM.beeps;i++)tone(SOM.freq,i*(SOM.dur+SOM.pausa),SOM.dur,SOM.vol)};
const sOk=()=>{tone(660,0,.08,.06,"sine");tone(990,.09,.14,.06,"sine")};

/* ---------- FOTO: recorta 3x4 (300x400) e comprime ---------- */
function lerFoto(file,cb){
  if(!file||!file.type.startsWith("image/")){err="Escolha um arquivo de imagem (JPG, PNG ou WebP).";return cb(null)}
  const r=new FileReader();
  r.onerror=()=>{err="Não foi possível ler a imagem.";cb(null)};
  r.onload=()=>{
    const im=new Image();
    im.onerror=()=>{err="Essa imagem não pôde ser aberta.";cb(null)};
    im.onload=()=>{
      const W=300,H=400,c=document.createElement("canvas");c.width=W;c.height=H;
      const g=c.getContext("2d"),sc=Math.max(W/im.width,H/im.height),w=im.width*sc,h=im.height*sc;
      g.fillStyle="#fff";g.fillRect(0,0,W,H);g.drawImage(im,(W-w)/2,(H-h)/2,w,h);
      cb(c.toDataURL("image/jpeg",.82));
    };
    im.src=r.result;
  };
  r.readAsDataURL(file);
}

/* ---------- NOVA ELEIÇÃO ---------- */
function setup(){
  const nova=E&&E.ativa;
  $("app").innerHTML=`<div class="card"><h1>${nova?"Nova eleição":"Configurar urna"}</h1>
  <p>Olá, ${esc(E.mesario)}. Defina o nome da eleição. As chapas e as fotos você cadastra na próxima tela.</p>
  ${nova?`<div class="note">A eleição atual será encerrada. Os votos dela continuam guardados no banco de dados.</div>`:""}
  <label for="ti">Nome da eleição</label><input type="text" id="ti" value="Eleição do Grêmio">
  ${err?`<div class="err">${esc(err)}</div>`:""}
  <button class="btn" id="go">Continuar e cadastrar chapas</button>
  ${nova?`<button class="btn sec" id="cc">Cancelar</button>`:`<button class="btn sec" id="sair">Sair</button>`}</div>`;
  $("go").onclick=async()=>{
    const r=await api("/api/eleicao","POST",{titulo:$("ti").value});
    if(r.status===401){await carregar();return}
    if(!r.ok){err=r.erro||"Erro ao criar a eleição.";return setup()}
    R=null;tab="chapas";editing=null;draft={n:"",name:"",img:""};await carregar();
  };
  if($("cc"))$("cc").onclick=()=>{view="admin";err="";admin()};
  if($("sair"))$("sair").onclick=sair;
}
async function sair(){await api("/api/admin/sair","POST");R=null;await carregar()}

/* ---------- LOGIN DO MESÁRIO ---------- */
function login(){
  $("app").innerHTML=`<div class="card"><h1>Área do mesário</h1>
  <p>${E.urna_liberada?"Entre para cadastrar chapas e ver o resultado.":"Esta urna ainda não foi liberada. Entre com o seu usuário e senha de mesário."}</p>
  <label for="u" style="margin-top:0">Usuário</label>
  <input type="text" id="u" autocomplete="username" autocapitalize="none" aria-label="Usuário">
  <label for="p">Senha</label>
  <input type="password" id="p" autocomplete="current-password" aria-label="Senha">
  ${err?`<div class="err">${esc(err)}</div>`:""}
  <button class="btn" id="ok">Entrar</button>
  ${E.urna_liberada&&E.chapas.length?`<button class="btn sec" id="vt">Voltar à votação</button>`:""}</div>`;
  $("ok").onclick=async()=>{
    const r=await api("/api/login","POST",{usuario:$("u").value,senha:$("p").value});
    if(!r.ok){err=r.erro||"Usuário ou senha incorretos.";return login()}
    tab="chapas";R=null;await carregar();
  };
  if($("vt"))$("vt").onclick=()=>{view="vote";render()};
  $("p").onkeydown=e=>{if(e.key==="Enter")$("ok").click()};
  $("u").focus();
}

/* ---------- URNA ---------- */
const maxLen=()=>Math.max(...E.chapas.map(c=>c.n.length));
function vote(){
  const len=maxLen(),found=E.chapas.find(c=>c.n===digits);
  let body;
  if(done)body=`<div class="big">FIM<br><span style="font-size:1.3rem;font-weight:600">Voto registrado</span></div>`;
  else if(blank)body=`<div class="big">VOTO EM BRANCO</div>`;
  else{
    let bx="";for(let i=0;i<len;i++)bx+=`<div class="box">${digits[i]||""}</div>`;
    let info="",foto="";
    if(digits.length===len){
      if(found){
        info=`<div class="nome">${esc(found.name)}</div>`;
        if(found.img)foto=`<div class="foto"><img src="${found.img}" alt="Foto da ${esc(found.name)}">Chapa ${esc(found.n)}</div>`;
      }else info=`<div class="nome">NÚMERO ERRADO<br>VOTO NULO</div>`;
    }
    body=`<div class="main"><div class="l"><div class="t">Seu voto para</div><div class="t" style="font-weight:700">${esc(E.titulo)}</div>
    <div>Número da chapa:</div><div class="boxes">${bx}</div>${info}</div>${foto}</div>`;
  }
  $("app").innerHTML=`<div class="urna"><div class="scr">${body}
  ${aviso?`<div class="aviso">${esc(aviso)}</div>`:""}
  <div class="rod">Aperte CONFIRMA para votar<br>CORRIGE para voltar e digitar de novo</div></div>
  <div class="pad"><div class="grid">${[1,2,3,4,5,6,7,8,9].map(n=>`<button class="k" data-d="${n}">${n}</button>`).join("")}<button class="k z" data-d="0">0</button></div>
  <div class="act"><button class="k b" id="kb">BRANCO</button><button class="k c" id="kc">CORRIGE</button><button class="k g" id="kg">CONFIRMA</button></div></div></div>
  <button class="mes" id="mes">Mesário</button>`;
  document.querySelectorAll("[data-d]").forEach(b=>b.onclick=()=>press(b.dataset.d));
  $("kb").onclick=branco;$("kc").onclick=corrige;$("kg").onclick=confirma;
  $("mes").onclick=()=>{clearTimeout(doneTimer);done=false;digits="";blank=false;aviso="";err="";view="login";render()};
}
function press(d){if(done||blank||busy||digits.length>=maxLen())return;aviso="";sTecla();digits+=d;vote()}
function corrige(){if(done||busy)return;digits="";blank=false;aviso="";sCorrige();vote()}
function branco(){if(done||busy)return;digits="";blank=true;aviso="";sBranco();vote()}
async function confirma(){
  if(done||busy)return;
  if(!blank&&digits.length<maxLen()){sErro();return}
  busy=true;
  const r=await api("/api/voto","POST",blank?{tipo:"branco"}:{tipo:"chapa",numero:digits});
  busy=false;
  if(!r.ok){
    sErro();
    if(r.status===403){await carregar();return}   // urna deixou de estar liberada
    aviso=(r.erro||"Não foi possível registrar o voto.")+" Seu voto NÃO foi gravado, tente confirmar de novo.";
    return vote();
  }
  aviso="";done=true;sConfirma();vote();
  doneTimer=setTimeout(()=>{done=false;digits="";blank=false;if(view==="vote")vote()},2600);
}
document.addEventListener("keydown",e=>{
  if(view!=="vote"||!E||!E.chapas.length)return;
  if(/^\d$/.test(e.key))press(e.key);
  else if(e.key==="Enter")confirma();
  else if(e.key==="Backspace")corrige();
});

/* ---------- ÁREA DO MESÁRIO ---------- */
async function sessaoExpirou(r){
  if(r.status===401||r.status===403){await carregar();return true}
  return false;
}
async function admin(){
  if(tab==="result"&&!R){
    const r=await api("/api/resultado");
    if(await sessaoExpirou(r))return;
    R=r;
  }
  const head=`<div class="card"><button class="btn sec sm" id="sair" style="float:right">Sair</button><h1>${esc(E.titulo)}</h1>
  <div class="tabs" role="tablist">
    <button class="tab" role="tab" id="t1" aria-selected="${tab==="chapas"}">Chapas</button>
    <button class="tab" role="tab" id="t2" aria-selected="${tab==="result"}">Resultado</button>
  </div>`;
  $("app").innerHTML=head+(tab==="chapas"?tabChapas():tabResultado())+`</div>`+(tab==="result"?boletim():"");
  $("sair").onclick=sair;
  $("t1").onclick=()=>{tab="chapas";err=msg="";admin()};
  $("t2").onclick=()=>{tab="result";R=null;err=msg="";admin()};
  tab==="chapas"?bindChapas():bindResultado();
}

/* --- aba Chapas --- */
function tabChapas(){
  const locked=E.travado;
  const lista=E.chapas.length?E.chapas.map((c,i)=>`<div class="row">
    ${c.img?`<img class="thumb" src="${c.img}" alt="">`:`<div class="thumb">sem foto</div>`}
    <div class="info"><b>${esc(c.n)} - ${esc(c.name)}</b></div>
    ${locked?"":`<button class="btn sec sm" data-ed="${i}">Editar</button><button class="btn red sm" data-rm="${i}">Remover</button>`}
  </div>`).join(""):`<p>Nenhuma chapa cadastrada ainda. Preencha o formulário acima para adicionar a primeira.</p>`;
  const form=locked?`<div class="note">A votação já começou, então as chapas estão travadas para não alterar o resultado. Para mudar algo, inicie uma nova eleição na aba Resultado.</div>`:`
  <h2>${editing!==null?"Editar chapa":"Adicionar chapa"}</h2>
  <div class="form">
    <div>
      <div class="drop" id="drop" tabindex="0" role="button" aria-label="Escolher foto da chapa">
        ${draft.img?`<img src="${draft.img}" alt="Prévia da foto">`:`<span>Toque para escolher<br>ou arraste uma foto</span>`}
      </div>
      <input type="file" id="file" accept="image/*" hidden>
      ${draft.img?`<button class="btn sec sm" id="rmimg" style="margin:8px 0 0">Remover foto</button>`:""}
    </div>
    <div>
      <label for="cn" style="margin-top:0">Número da chapa</label>
      <input type="text" id="cn" inputmode="numeric" maxlength="4" value="${esc(draft.n)}" placeholder="ex.: 11">
      <label for="cm">Nome da chapa</label>
      <input type="text" id="cm" value="${esc(draft.name)}" placeholder="ex.: Renovação">
      ${err?`<div class="err">${esc(err)}</div>`:""}${msg?`<div class="ok">${esc(msg)}</div>`:""}
      <button class="btn" id="sv">${editing!==null?"Salvar alterações":"Adicionar chapa"}</button>
      ${editing!==null?`<button class="btn sec" id="cc">Cancelar</button>`:""}
    </div>
  </div>
  <h2>Chapas cadastradas (${E.chapas.length})</h2>`;
  return form+(locked?`<h2>Chapas cadastradas (${E.chapas.length})</h2>`:"")+lista+`
  <div style="margin-top:10px"><button class="btn" id="ini" ${E.chapas.length?"":"disabled"}>Liberar urna e iniciar votação</button></div>`;
}
function lerDraft(){if($("cn")){draft.n=$("cn").value.replace(/\D/g,"");draft.name=$("cm").value}}
function bindChapas(){
  if(!E.travado){
    const drop=$("drop"),file=$("file");
    drop.onclick=()=>file.click();
    drop.onkeydown=e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();file.click()}};
    const pegar=f=>{lerDraft();err=msg="";lerFoto(f,d=>{if(d)draft.img=d;admin()})};
    file.onchange=()=>pegar(file.files[0]);
    drop.ondragover=e=>{e.preventDefault();drop.classList.add("over")};
    drop.ondragleave=()=>drop.classList.remove("over");
    drop.ondrop=e=>{e.preventDefault();drop.classList.remove("over");pegar(e.dataTransfer.files[0])};
    if($("rmimg"))$("rmimg").onclick=()=>{lerDraft();draft.img="";admin()};
    $("sv").onclick=salvarChapa;
    $("cm").onkeydown=e=>{if(e.key==="Enter")salvarChapa()};
    if($("cc"))$("cc").onclick=()=>{editing=null;draft={n:"",name:"",img:""};err=msg="";admin()};
    document.querySelectorAll("[data-ed]").forEach(b=>b.onclick=()=>{
      editing=+b.dataset.ed;const c=E.chapas[editing];draft={n:c.n,name:c.name,img:c.img||""};err=msg="";admin();
      window.scrollTo({top:0,behavior:"smooth"});
    });
    document.querySelectorAll("[data-rm]").forEach(b=>b.onclick=async()=>{
      const c=E.chapas[+b.dataset.rm];
      if(!confirm(`Remover a chapa ${c.n} - ${c.name}?`))return;
      const r=await api("/api/chapas/"+encodeURIComponent(c.n),"DELETE");
      if(await sessaoExpirou(r))return;
      if(!r.ok)err=r.erro;
      editing=null;draft={n:"",name:"",img:""};await recarregarEstado();
    });
  }
  $("ini").onclick=async()=>{
    const r=await api("/api/urna/liberar","POST");
    if(await sessaoExpirou(r))return;
    if(!r.ok){err=r.erro;return admin()}
    digits="";blank=false;done=false;await carregar();
  };
}
async function recarregarEstado(){E=await api("/api/estado");admin()}
async function salvarChapa(){
  lerDraft();err=msg="";
  const corpo={numero:draft.n,nome:draft.name,img:draft.img};
  const r=editing!==null
    ?await api("/api/chapas/"+encodeURIComponent(E.chapas[editing].n),"PUT",corpo)
    :await api("/api/chapas","POST",corpo);
  if(await sessaoExpirou(r))return;
  if(!r.ok){err=r.erro||"Não foi possível salvar a chapa.";return admin()}
  sOk();msg=editing!==null?"Chapa atualizada.":"Chapa adicionada.";
  editing=null;draft={n:"",name:"",img:""};await recarregarEstado();
}

/* --- aba Resultado --- */
function tabResultado(){
  const max=Math.max(0,...R.chapas.map(r=>r.v));
  const lideres=R.chapas.filter(r=>r.v===max&&max>0).length;
  return `<table><tr><th>Chapa</th><th>Votos</th></tr>
  ${R.chapas.map(r=>`<tr><td>${esc(r.n)} - ${esc(r.name)}${r.v===max&&max>0?(lideres>1?" (empate)":" ✔"):""}
    <div class="bar"><i style="width:${R.total?Math.round(r.v/R.total*100):0}%"></i></div></td><td>${r.v}</td></tr>`).join("")}
  <tr><td>Brancos</td><td>${R.branco}</td></tr><tr><td>Nulos</td><td>${R.nulo}</td></tr>
  <tr><td><b>Total de votos</b></td><td><b>${R.total}</b></td></tr></table>
  <div style="margin-top:10px">
  <button class="btn" id="pr">Imprimir resultado</button>
  <a class="btn sec" style="display:inline-block;text-decoration:none" href="/api/resultado.csv">Baixar CSV</a>
  <button class="btn sec" id="vt">Voltar à votação</button>
  <button class="btn red" id="rs">Nova eleição</button></div>
  <div class="note">Dica: antes de começar outra eleição, imprima o resultado ou baixe o CSV. Os dados antigos continuam no banco, mas somem desta tela.</div>`;
}
function boletim(){
  const d=new Date().toLocaleString("pt-BR");
  return `<div id="boletim"><h1>${esc(R.titulo)}</h1><div class="sub">Boletim de resultado - emitido em ${d}</div>
  <table><tr><th>Chapa</th><th>Votos</th></tr>
  ${R.chapas.map(r=>`<tr><td>${esc(r.n)} - ${esc(r.name)}</td><td>${r.v}</td></tr>`).join("")}
  <tr><td>Votos em branco</td><td>${R.branco}</td></tr><tr><td>Votos nulos</td><td>${R.nulo}</td></tr>
  <tr class="tot"><td>Total de votos</td><td>${R.total}</td></tr></table>
  <div class="assin"><div>Mesário</div><div>Presidente da comissão</div></div></div>`;
}
function bindResultado(){
  $("pr").onclick=()=>{try{window.print()}catch(e){alert("Use Ctrl+P para imprimir.")}};
  $("vt").onclick=async()=>{
    const r=await api("/api/urna/liberar","POST");
    if(await sessaoExpirou(r))return;
    if(!r.ok){err=r.erro;return admin()}
    digits="";blank=false;done=false;R=null;await carregar();
  };
  $("rs").onclick=()=>{view="setup";err="";render()};   // pede o título da nova eleição
}

carregar();
if("serviceWorker" in navigator)window.addEventListener("load",()=>navigator.serviceWorker.register("/sw.js").catch(()=>{}));

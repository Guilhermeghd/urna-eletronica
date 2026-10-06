"use strict";
/* Painel do dono: cadastra e gerencia as contas de mesário (/api/dono/...). */

const esc=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const $=id=>document.getElementById(id);
let S=null,lista=[],err="",msg="";

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
  S=await api("/api/dono/estado");
  if(S.logado){
    const r=await api("/api/dono/mesarios");
    if(r.status===401){S.logado=false}else lista=r.mesarios||[];
  }
  S.logado?painel():login();
}
function login(){
  $("app").innerHTML=`<div class="card"><h1>Painel do administrador</h1>
  <p>Área restrita: só o administrador do sistema cadastra mesários.</p>
  ${S.habilitado?"":`<div class="err">Painel desabilitado: defina ADMIN_PASSWORD no servidor.</div>`}
  <label for="u">Usuário</label><input type="text" id="u" autocomplete="username">
  <label for="s">Senha</label><input type="password" id="s" autocomplete="current-password">
  ${err?`<div class="err">${esc(err)}</div>`:""}
  <button class="btn" id="ok">Entrar</button></div>`;
  $("ok").onclick=async()=>{
    const r=await api("/api/dono/login","POST",{usuario:$("u").value,senha:$("s").value});
    if(!r.ok){err=r.erro||"Erro ao entrar.";return login()}
    err="";await carregar();
  };
  $("s").onkeydown=e=>{if(e.key==="Enter")$("ok").click()};
  $("u").focus();
}
function painel(){
  $("app").innerHTML=`<div class="card"><h1>Mesários</h1>
  <p>Cada mesário (escola) tem login próprio e só enxerga as próprias eleições.</p>
  <h2>Novo mesário</h2>
  <label for="nm" style="margin-top:0">Nome da escola / mesário</label><input type="text" id="nm" maxlength="80">
  <label for="us">Usuário (para entrar)</label><input type="text" id="us" maxlength="30" autocomplete="off" placeholder="ex.: escola.centro">
  <label for="pw">Senha (mínimo 6 caracteres)</label><input type="text" id="pw" autocomplete="off">
  ${err?`<div class="err">${esc(err)}</div>`:""}${msg?`<div class="ok">${esc(msg)}</div>`:""}
  <button class="btn" id="cr">Cadastrar mesário</button>
  <h2>Cadastrados (${lista.length})</h2>
  ${lista.length?lista.map(m=>`<div class="row">
    <div class="info"><b>${esc(m.nome)}${m.ativo?"":" (desativado)"}</b>
    <span>${esc(m.usuario)} · ${m.eleicoes} eleição(ões)</span></div>
    <button class="btn sec sm" data-pw="${m.id}">Nova senha</button>
    <button class="btn ${m.ativo?"red":""} sm" data-at="${m.id}">${m.ativo?"Desativar":"Ativar"}</button>
  </div>`).join(""):`<p>Nenhum mesário cadastrado ainda.</p>`}
  <button class="btn sec" id="sair">Sair</button></div>`;
  $("cr").onclick=async()=>{
    err=msg="";
    const r=await api("/api/dono/mesarios","POST",{nome:$("nm").value,usuario:$("us").value,senha:$("pw").value});
    if(r.status===401)return carregar();
    if(!r.ok)err=r.erro||"Não foi possível cadastrar.";else msg="Mesário cadastrado. Passe o usuário e a senha para ele.";
    await carregar();
  };
  document.querySelectorAll("[data-pw]").forEach(b=>b.onclick=async()=>{
    const m=lista.find(x=>x.id==b.dataset.pw),s=prompt(`Nova senha para ${m.usuario} (mínimo 6 caracteres):`);
    if(!s)return;
    const r=await api("/api/dono/mesarios/"+m.id,"PATCH",{senha:s});
    err=r.ok?"":(r.erro||"Erro.");msg=r.ok?"Senha alterada.":"";
    await carregar();
  });
  document.querySelectorAll("[data-at]").forEach(b=>b.onclick=async()=>{
    const m=lista.find(x=>x.id==b.dataset.at);
    const r=await api("/api/dono/mesarios/"+m.id,"PATCH",{ativo:!m.ativo});
    err=r.ok?"":(r.erro||"Erro.");msg="";
    await carregar();
  });
  $("sair").onclick=async()=>{await api("/api/dono/sair","POST");err=msg="";await carregar()};
}
carregar();

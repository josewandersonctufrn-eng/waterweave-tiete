"""Componente 3D cinematográfico (Three.js/WebGL) do ciclo poluição->restauração do Rio Tietê.

Cena estilizada em tempo real (não fotorrealismo de VFX de longa-metragem —
isso exigiria produção offline em Blender/Houdini + Unreal, incompatível com
resposta ao vivo aos sliders do usuário). 100% pilotada pelos dados REAIS
simulados pelo ABM (`models.abm.scenarios.rodar_cenario_customizado` +
`models.biofisico.parametros_estendidos`): cor/turbidez da água, iluminação,
partículas de sedimento/espuma/bolhas, tubulação industrial, peixes e
vegetação respondem aos valores simulados de cada ano, não a uma animação
solta.

Uso:
    from waterweave.webapp.components.rio_3d import renderizar_html
    html = renderizar_html(dados_por_ano, ano_min=1, ano_max=15)
    st.components.v1.html(html, height=640, scrolling=False)
"""
from __future__ import annotations

import json

_TEMPLATE = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body { margin: 0; padding: 0; overflow: hidden; background: #0c0f14; font-family: 'Inter', -apple-system, 'Segoe UI', sans-serif; }
  #cena { width: 100%; height: __ALTURA__px; display: block; }
  #painel {
    position: absolute; left: 16px; top: 14px; color: #f2f1ee; z-index: 10;
    text-shadow: 0 1px 4px rgba(0,0,0,0.6); pointer-events: none;
  }
  #painel .ano { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; }
  #painel .fase { font-size: 14px; opacity: 0.9; margin-top: 2px; }
  #metricas {
    position: absolute; right: 16px; top: 14px; color: #f2f1ee; z-index: 10;
    text-align: right; font-size: 12px; line-height: 1.5; text-shadow: 0 1px 4px rgba(0,0,0,0.6);
    pointer-events: none; opacity: 0.92;
  }
  #controles {
    position: absolute; left: 0; right: 0; bottom: 0; padding: 10px 18px 14px;
    background: linear-gradient(to top, rgba(0,0,0,0.55), transparent); z-index: 10;
    display: flex; align-items: center; gap: 12px;
  }
  #controles button {
    background: rgba(255,255,255,0.14); border: 1px solid rgba(255,255,255,0.3); color: #f2f1ee;
    border-radius: 999px; width: 34px; height: 34px; cursor: pointer; font-size: 14px;
    display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  }
  #controles button:hover { background: rgba(255,255,255,0.26); }
  #slider { flex: 1; accent-color: #1baf7a; }
  #toggleWrap { display: flex; align-items: center; gap: 6px; color: #f2f1ee; font-size: 12px; flex-shrink: 0; }
  #cenaWrap { position: relative; width: 100%; }
  #carregando {
    position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
    color: #cfe8ff; font-size: 13px; z-index: 20; background: #0c0f14;
  }
</style>
</head>
<body>
<div id="cenaWrap">
  <div id="carregando">Carregando cena…</div>
  <div id="painel"><div class="ano">Ano 0</div><div class="fase">—</div></div>
  <div id="metricas"></div>
  <canvas id="cena"></canvas>
  <div id="controles">
    <button id="btnPlay" title="Reproduzir/Pausar">▶</button>
    <input id="slider" type="range" min="__ANO_MIN__" max="__ANO_MAX__" value="__ANO_MIN__" step="1">
    <div id="toggleWrap">
      <label><input type="checkbox" id="chkNaoControlado"> ver sem controle</label>
    </div>
  </div>
</div>

<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
<script>
const DADOS = __DADOS_JSON__;
const ANO_MIN = __ANO_MIN__;
const ANO_MAX = __ANO_MAX__;

function buscarLinha(serie, ano) {
  let melhor = serie[0];
  for (const l of serie) { if (l.ano <= ano) melhor = l; else break; }
  return melhor;
}

function fase(iqaAtual, iqaAnterior) {
  if (iqaAtual >= 70) return (iqaAnterior === null || iqaAnterior >= 65) ? "Água limpa" : "Recuperação concluída";
  if (iqaAnterior !== null && iqaAtual - iqaAnterior > 1.5) return "Tratamento em ação — recuperando";
  if (iqaAnterior !== null && iqaAtual - iqaAnterior < -1.5) return "Poluição avançando";
  return "Estado crítico estável";
}

// ---------------------------------------------------------------------------
// Cena
// ---------------------------------------------------------------------------
const canvas = document.getElementById('cena');
const wrap = document.getElementById('cenaWrap');
const ALTURA = __ALTURA__;

const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(wrap.clientWidth, ALTURA);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, wrap.clientWidth / ALTURA, 0.1, 200);

const hemi = new THREE.HemisphereLight(0xbfd8ff, 0x3a3226, 0.55);
scene.add(hemi);
const sol = new THREE.DirectionalLight(0xffffff, 1.4);
sol.position.set(-8, 12, 6);
scene.add(sol);

scene.fog = new THREE.FogExp2(0x9fb8c8, 0.018);

// Terreno / margens (verde -> marrom conforme severidade)
const terrenoGeo = new THREE.PlaneGeometry(60, 34, 40, 24);
const terrenoMat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 1.0 });
const posAttr = terrenoGeo.attributes.position;
const cores = new Float32Array(posAttr.count * 3);
for (let i = 0; i < posAttr.count; i++) {
  const x = posAttr.getX(i);
  const z = Math.abs(posAttr.getY(i));
  posAttr.setZ(i, Math.sin(x * 0.15) * 0.12 + Math.random() * 0.04);
  const margemFactor = Math.min(1, z / 9);
  cores[i * 3] = 0.30 + margemFactor * 0.25;
  cores[i * 3 + 1] = 0.45;
  cores[i * 3 + 2] = 0.22;
}
terrenoGeo.setAttribute('color', new THREE.BufferAttribute(cores, 3));
terrenoGeo.computeVertexNormals();
const terreno = new THREE.Mesh(terrenoGeo, terrenoMat);
terreno.rotation.x = -Math.PI / 2;
terreno.position.y = -0.3;
scene.add(terreno);

// Água
const AGUA_LARGURA = 13.0;
const aguaGeo = new THREE.PlaneGeometry(60, AGUA_LARGURA, 120, 30);
const aguaUniforms = {
  uTime: { value: 0 },
  uSeverity: { value: 0.0 },
  uTurbidez: { value: 0.1 },
  uCorLimpa: { value: new THREE.Color(0x1c7fae) },
  uCorPoluida: { value: new THREE.Color(0x5a4a34) },
};
const aguaMat = new THREE.ShaderMaterial({
  uniforms: aguaUniforms,
  transparent: true,
  vertexShader: `
    uniform float uTime;
    uniform float uSeverity;
    varying vec2 vUv;
    varying float vOnda;
    void main() {
      vUv = uv;
      vec3 p = position;
      float onda = sin(p.x * 0.5 + uTime * 1.1) * 0.08 + sin(p.y * 0.8 - uTime * 0.7) * 0.05;
      onda *= (1.0 - uSeverity * 0.5);
      p.z += onda;
      vOnda = onda;
      gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
    }
  `,
  fragmentShader: `
    uniform float uSeverity;
    uniform float uTurbidez;
    uniform vec3 uCorLimpa;
    uniform vec3 uCorPoluida;
    varying vec2 vUv;
    varying float vOnda;
    float ruido(vec2 c){ return fract(sin(dot(c, vec2(12.9898,78.233))) * 43758.5453); }
    void main() {
      float misturaCor = pow(uSeverity, 0.6);
      vec3 cor = mix(uCorLimpa, uCorPoluida, misturaCor);
      float brilho = smoothstep(0.02, 0.09, vOnda) * (1.0 - uSeverity * 0.6);
      cor += brilho * 0.35;
      float espumaRuido = ruido(floor(vUv * 90.0));
      float espuma = step(0.965, espumaRuido) * smoothstep(0.3, 0.9, uSeverity);
      cor = mix(cor, vec3(0.75, 0.72, 0.62), espuma);
      float alpha = 0.82 + uTurbidez * 0.16;
      gl_FragColor = vec4(cor, alpha);
    }
  `,
});
const agua = new THREE.Mesh(aguaGeo, aguaMat);
agua.rotation.x = -Math.PI / 2;
scene.add(agua);

// Tubulação industrial (fonte de poluição)
const tuboGeo = new THREE.CylinderGeometry(0.45, 0.45, 3.2, 16);
const tuboMat = new THREE.MeshStandardMaterial({ color: 0x6b6b6b, roughness: 0.6, metalness: 0.4 });
const tubo = new THREE.Mesh(tuboGeo, tuboMat);
tubo.rotation.z = Math.PI / 2;
tubo.position.set(-9, 0.6, 5.6);
scene.add(tubo);

// Partículas: despejo poluente (tubo -> água)
const N_DESPEJO = 260;
const despejoGeo = new THREE.BufferGeometry();
const despejoPos = new Float32Array(N_DESPEJO * 3);
const despejoSeed = new Float32Array(N_DESPEJO);
for (let i = 0; i < N_DESPEJO; i++) { despejoSeed[i] = Math.random(); }
despejoGeo.setAttribute('position', new THREE.BufferAttribute(despejoPos, 3));
const despejoMat = new THREE.PointsMaterial({ color: 0x3a2f22, size: 0.22, transparent: true, opacity: 0.0, depthWrite: false });
const despejo = new THREE.Points(despejoGeo, despejoMat);
scene.add(despejo);

// Partículas: bolhas de oxigenação (tratamento/OD saudável)
const N_BOLHAS = 180;
const bolhasGeo = new THREE.BufferGeometry();
const bolhasPos = new Float32Array(N_BOLHAS * 3);
const bolhasSeed = new Float32Array(N_BOLHAS);
for (let i = 0; i < N_BOLHAS; i++) {
  bolhasPos[i*3] = (Math.random() - 0.5) * 30;
  bolhasPos[i*3+1] = -Math.random() * 1.5;
  bolhasPos[i*3+2] = (Math.random() - 0.5) * (AGUA_LARGURA - 1);
  bolhasSeed[i] = Math.random();
}
bolhasGeo.setAttribute('position', new THREE.BufferAttribute(bolhasPos, 3));
const bolhasMat = new THREE.PointsMaterial({ color: 0xdff6ff, size: 0.12, transparent: true, opacity: 0.0, depthWrite: false });
const bolhas = new THREE.Points(bolhasGeo, bolhasMat);
scene.add(bolhas);

// Peixes (proxy simplificado de vida aquática — não fotorrealista)
const N_PEIXES = 7;
const peixes = [];
const peixeShape = new THREE.ConeGeometry(0.16, 0.55, 6);
peixeShape.rotateZ(Math.PI / 2);
for (let i = 0; i < N_PEIXES; i++) {
  const m = new THREE.Mesh(peixeShape, new THREE.MeshStandardMaterial({ color: 0x6fa8c9, roughness: 0.5 }));
  m.userData = { raio: 3 + Math.random() * 7, vel: 0.3 + Math.random() * 0.4, fase: Math.random() * Math.PI * 2, prof: -0.4 - Math.random() * 1.6 };
  scene.add(m);
  peixes.push(m);
}

// Vegetação (touceiras simples nas margens)
const N_VEG = 26;
const vegetacao = [];
const vegGeo = new THREE.ConeGeometry(0.35, 1.1, 5);
for (let i = 0; i < N_VEG; i++) {
  const lado = i % 2 === 0 ? 1 : -1;
  const m = new THREE.Mesh(vegGeo, new THREE.MeshStandardMaterial({ color: 0x4a8a3a, roughness: 1.0 }));
  m.position.set(-27 + (i / N_VEG) * 54 + (Math.random()-0.5)*1.5, 0.4, lado * (7.2 + Math.random() * 2.2));
  m.scale.setScalar(0.7 + Math.random() * 0.6);
  scene.add(m);
  vegetacao.push(m);
}

camera.position.set(0, 11.5, 23);
camera.lookAt(0, 0, 0);

// ---------------------------------------------------------------------------
// Estado / animação
// ---------------------------------------------------------------------------
let anoAtual = ANO_MIN;
let tocando = false;
let corAnterior = null;

function metricaLinha(nome, valor, unidade) {
  return nome + ": <b>" + valor + (unidade ? (" " + unidade) : "") + "</b>";
}

function atualizarParaAno(ano) {
  const usarNaoControlado = document.getElementById('chkNaoControlado').checked;
  const serie = usarNaoControlado ? DADOS.nao_controlado : DADOS.controlado;
  const linha = buscarLinha(serie, ano);
  const linhaAnterior = ano > ANO_MIN ? buscarLinha(serie, ano - 1) : null;

  const severidade = Math.max(0, Math.min(1, (100 - linha.iqa) / 100));
  const turbidezNorm = Math.max(0, Math.min(1, linha.turbidez_ntu / 45.0));
  const odNorm = Math.max(0, Math.min(1, linha.od_mg_l / 8.0));
  const bioticoNorm = Math.max(0, Math.min(1, linha.indice_biotico / 100.0));

  aguaUniforms.uSeverity.value = severidade;
  aguaUniforms.uTurbidez.value = turbidezNorm;

  // Iluminação: quente/brilhante (limpo) <-> fria/opaca (poluído)
  const corSolLimpo = new THREE.Color(0xfff3d6);
  const corSolPoluido = new THREE.Color(0x8fa3ad);
  sol.color.copy(corSolLimpo).lerp(corSolPoluido, severidade);
  sol.intensity = 1.6 - severidade * 0.9;
  const corFogLimpo = new THREE.Color(0xbfe0f5);
  const corFogPoluido = new THREE.Color(0x7c7566);
  const corFogAtual = corFogLimpo.clone().lerp(corFogPoluido, severidade);
  scene.fog.color.copy(corFogAtual);
  renderer.setClearColor(corFogAtual, 1.0);

  // Despejo da tubulação: ativo proporcional à severidade (fonte poluidora ainda ativa)
  despejoMat.opacity = 0.55 * severidade;

  // Bolhas de oxigenação: proporcional ao OD real
  bolhasMat.opacity = 0.75 * odNorm;

  // Vegetação: verde viçoso <-> seco/acastanhado
  const corVegVivo = new THREE.Color(0x4a8a3a);
  const corVegSeca = new THREE.Color(0x6b5a34);
  vegetacao.forEach((v) => {
    v.material.color.copy(corVegVivo).lerp(corVegSeca, severidade);
    v.scale.y = 0.7 + bioticoNorm * 0.5;
  });

  // Peixes: visíveis/ativos conforme índice biótico
  peixes.forEach((p) => {
    p.visible = bioticoNorm > 0.12;
    p.userData.profAlvo = -0.4 - (1 - bioticoNorm) * 1.6;
  });

  document.querySelector('#painel .ano').textContent = "Ano " + ano;
  document.querySelector('#painel .fase').textContent = fase(linha.iqa, linhaAnterior ? linhaAnterior.iqa : null)
    + (usarNaoControlado ? "  ·  cenário não controlado" : "  ·  cenário controlado");
  document.getElementById('metricas').innerHTML = [
    metricaLinha("IQA", linha.iqa.toFixed(0)),
    metricaLinha("OD", linha.od_mg_l.toFixed(2), "mg/L"),
    metricaLinha("DBO", linha.dbo_mg_l.toFixed(1), "mg/L"),
    metricaLinha("Turbidez", linha.turbidez_ntu.toFixed(0), "NTU"),
    metricaLinha("E. coli", Math.round(linha.e_coli_nmp_100ml).toLocaleString('pt-BR'), "NMP/100mL"),
    metricaLinha("Índice biótico", linha.indice_biotico.toFixed(0)),
  ].join("<br>");

  document.getElementById('slider').value = ano;
}

document.getElementById('slider').addEventListener('input', (e) => {
  anoAtual = parseInt(e.target.value, 10);
  atualizarParaAno(anoAtual);
});
document.getElementById('chkNaoControlado').addEventListener('change', () => atualizarParaAno(anoAtual));

let intervaloPlay = null;
document.getElementById('btnPlay').addEventListener('click', (e) => {
  tocando = !tocando;
  e.target.textContent = tocando ? "⏸" : "▶";
  if (tocando) {
    intervaloPlay = setInterval(() => {
      anoAtual = anoAtual >= ANO_MAX ? ANO_MIN : anoAtual + 1;
      atualizarParaAno(anoAtual);
    }, 900);
  } else {
    clearInterval(intervaloPlay);
  }
});

function aoRedimensionar() {
  const largura = wrap.clientWidth;
  camera.aspect = largura / ALTURA;
  camera.updateProjectionMatrix();
  renderer.setSize(largura, ALTURA);
}
window.addEventListener('resize', aoRedimensionar);

let t = 0;
function loop() {
  requestAnimationFrame(loop);
  t += 0.016;
  aguaUniforms.uTime.value = t;

  // câmera: órbita suave contínua ("plano fluido")
  const raioCam = 24.0 + Math.sin(t * 0.05) * 1.5;
  camera.position.x = Math.sin(t * 0.05) * raioCam * 0.5;
  camera.position.z = Math.cos(t * 0.05) * raioCam * 0.5 + 6;
  camera.position.y = 10.5 + Math.sin(t * 0.04) * 1.0;
  camera.lookAt(0, -0.3, 0);

  // despejo: partículas descendo/espalhando a partir do tubo
  const dp = despejoGeo.attributes.position.array;
  for (let i = 0; i < N_DESPEJO; i++) {
    const s = despejoSeed[i];
    const vida = (t * (0.25 + s * 0.3) + s * 10) % 6.0;
    dp[i*3] = -9 + vida * 1.6 + Math.sin(s * 40 + t) * 0.3;
    dp[i*3+1] = 0.3 - vida * 0.06;
    dp[i*3+2] = 5.6 - vida * 0.4 + Math.sin(s * 20) * vida * 0.5;
  }
  despejoGeo.attributes.position.needsUpdate = true;

  // bolhas subindo
  const bp = bolhasGeo.attributes.position.array;
  for (let i = 0; i < N_BOLHAS; i++) {
    const s = bolhasSeed[i];
    bp[i*3+1] += 0.01 + s * 0.01;
    if (bp[i*3+1] > 0.6) bp[i*3+1] = -1.6;
  }
  bolhasGeo.attributes.position.needsUpdate = true;

  // peixes nadando
  peixes.forEach((p) => {
    const u = p.userData;
    u.fase += 0.016 * u.vel;
    p.position.x = Math.sin(u.fase) * u.raio;
    p.position.z = Math.cos(u.fase) * u.raio * 0.5;
    p.position.y += ((u.profAlvo !== undefined ? u.profAlvo : u.prof) - p.position.y) * 0.02;
    p.rotation.y = -u.fase + Math.PI / 2;
  });

  renderer.render(scene, camera);
}

aoRedimensionar();
atualizarParaAno(ANO_MIN);
document.getElementById('carregando').style.display = 'none';
loop();
</script>
</body>
</html>
"""


def renderizar_html(dados_controlado: list[dict], dados_nao_controlado: list[dict], ano_min: int, ano_max: int, altura_px: int = 620) -> str:
    """Monta o HTML final do componente, injetando as trajetórias reais simuladas (controlado e
    não controlado) — o JS só lê esses dados, nunca gera valores por conta própria."""
    payload = {"controlado": dados_controlado, "nao_controlado": dados_nao_controlado}
    html = _TEMPLATE
    html = html.replace("__DADOS_JSON__", json.dumps(payload, ensure_ascii=False))
    html = html.replace("__ANO_MIN__", str(ano_min))
    html = html.replace("__ANO_MAX__", str(ano_max))
    html = html.replace("__ALTURA__", str(altura_px))
    return html

"""Componente 3D cinematográfico (Three.js/WebGL) do ciclo poluição->restauração do Rio Tietê.

Cena estilizada em tempo real (não fotorrealismo de VFX de longa-metragem —
isso exigiria produção offline em Blender/Houdini + Unreal, incompatível com
resposta ao vivo aos sliders do usuário). 100% pilotada pelos dados REAIS
simulados pelo ABM (`models.abm.scenarios.rodar_cenario_customizado` +
`models.biofisico.parametros_estendidos`).

Mapeamento variável -> elemento visual (arquitetura do sistema):

    Turbidez                         -> cor/opacidade da água (uSeverity/uTurbidez)
    Turbidez + chuva + baixo esforço -> partículas de lama (plantação -> rio)
    Sólidos Totais                   -> camada de assoreamento no leito
    OD                                -> peixes (vivos, letárgicos ou de barriga p/ cima)
    DBO/severidade + Metais           -> espuma química + filme de óleo na superfície
    pH (distância de 7)               -> vegetação marginal murcha (+ severidade)
    Nutrientes (Fósforo+Nitrogênio)   -> floração de algas na superfície (eutrofização)
    Vazão (normalizada na sessão)     -> nível d'água, largura do canal, bancos de areia
    Índice de escoamento (chuva real) -> sistema de partículas de chuva
    Esgoto industrial/doméstico       -> 2 tubulações com despejo (indústria + residências)

Uso:
    from waterweave.webapp.components.rio_3d import renderizar_html
    html = renderizar_html(dados_controlado, dados_nao_controlado, ano_min=1, ano_max=15)
    st.components.v1.html(html, height=680, scrolling=False)
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
  #legenda {
    position: absolute; left: 16px; bottom: 54px; color: #f2f1ee; z-index: 10; font-size: 10.5px;
    text-shadow: 0 1px 3px rgba(0,0,0,0.7); opacity: 0.85; pointer-events: none; line-height: 1.5;
  }
  #dicaCamera {
    position: absolute; right: 16px; bottom: 54px; color: #f2f1ee; z-index: 10; font-size: 10.5px;
    text-shadow: 0 1px 3px rgba(0,0,0,0.7); opacity: 0; pointer-events: none; text-align: right;
    transition: opacity 0.6s ease;
  }
  #cena { touch-action: none; }
</style>
</head>
<body>
<div id="cenaWrap">
  <div id="carregando">__CARREGANDO__</div>
  <div id="painel"><div class="ano">__ANO_LABEL__ 0</div><div class="fase">—</div></div>
  <div id="metricas"></div>
  <div id="legenda">__LEGENDA__</div>
  <div id="dicaCamera">__DICA_CAMERA__</div>
  <canvas id="cena"></canvas>
  <div id="controles">
    <button id="btnPlay" title="__BOTAO_REPRODUZIR__">▶</button>
    <input id="slider" type="range" min="__ANO_MIN__" max="__ANO_MAX__" value="__ANO_MIN__" step="1">
    <div id="toggleWrap">
      <label><input type="checkbox" id="chkNaoControlado"> __VER_SEM_CONTROLE__</label>
    </div>
  </div>
</div>

<script src="https://unpkg.com/three@0.160.0/build/three.min.js"></script>
<script>
const DADOS = __DADOS_JSON__;
const TEXTOS = __TEXTOS_JSON__;
const ANO_MIN = __ANO_MIN__;
const ANO_MAX = __ANO_MAX__;

function buscarLinha(serie, ano) {
  let melhor = serie[0];
  for (const l of serie) { if (l.ano <= ano) melhor = l; else break; }
  return melhor;
}

function fase(iqaAtual, iqaAnterior) {
  if (iqaAtual >= 70) return (iqaAnterior === null || iqaAnterior >= 65) ? TEXTOS.fase_agua_limpa : TEXTOS.fase_recuperacao;
  if (iqaAnterior !== null && iqaAtual - iqaAnterior > 1.5) return TEXTOS.fase_tratamento;
  if (iqaAnterior !== null && iqaAtual - iqaAnterior < -1.5) return TEXTOS.fase_poluicao;
  return TEXTOS.fase_critico;
}

// Faixas reais (ambas as séries) para normalizar vazão e chuva de forma consistente --------
function faixa(chave) {
  const valores = [...DADOS.controlado, ...DADOS.nao_controlado].map(l => l[chave]).filter(v => v !== undefined && v !== null);
  return { min: Math.min(...valores), max: Math.max(...valores) };
}
const FAIXA_VAZAO = faixa('vazao_m3s_medio');
const FAIXA_ESCOAMENTO = faixa('indice_escoamento_mm');

function normalizar(valor, faixaObj) {
  const amplitude = faixaObj.max - faixaObj.min;
  if (amplitude < 1e-6) return 0.5;
  return Math.max(0, Math.min(1, (valor - faixaObj.min) / amplitude));
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

scene.fog = new THREE.FogExp2(0x9fb8c8, 0.016);

// Terreno / margens (verde -> marrom conforme severidade)
const terrenoGeo = new THREE.PlaneGeometry(72, 40, 40, 24);
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

// Água (nível/largura variam com a vazão simulada — ver atualizarNivelAgua)
const AGUA_LARGURA = 13.0;
const aguaGeo = new THREE.PlaneGeometry(66, AGUA_LARGURA, 120, 30);
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

// Camada de assoreamento no leito (visível através da água quando Sólidos Totais sobem)
const sedimentoLeitoGeo = new THREE.PlaneGeometry(66, AGUA_LARGURA - 1, 1, 1);
const sedimentoLeitoMat = new THREE.MeshBasicMaterial({ color: 0x4a3a26, transparent: true, opacity: 0.0 });
const sedimentoLeito = new THREE.Mesh(sedimentoLeitoGeo, sedimentoLeitoMat);
sedimentoLeito.rotation.x = -Math.PI / 2;
sedimentoLeito.position.y = -0.18;
scene.add(sedimentoLeito);

// Bancos de areia/pedra expostos quando a vazão cai abaixo do necessário
const bancosAreia = [];
const bancoGeo = new THREE.SphereGeometry(1, 12, 6);
const posicoesBanco = [[-14, -1.5], [3, 2.0], [16, -1.0]];
for (const [bx, bz] of posicoesBanco) {
  const m = new THREE.Mesh(bancoGeo, new THREE.MeshStandardMaterial({ color: 0xcbb583, roughness: 1.0 }));
  m.position.set(bx, -0.55, bz);
  m.scale.set(2.4, 0.22, 1.5);
  m.visible = false;
  scene.add(m);
  bancosAreia.push(m);
}

// Tubulação industrial + fábrica (fonte de poluição pontual)
const tuboGeo = new THREE.CylinderGeometry(0.45, 0.45, 3.2, 16);
const tuboMat = new THREE.MeshStandardMaterial({ color: 0x6b6b6b, roughness: 0.6, metalness: 0.4 });
const tubo = new THREE.Mesh(tuboGeo, tuboMat);
tubo.rotation.z = Math.PI / 2;
tubo.position.set(-11, 0.6, 5.6);
scene.add(tubo);

const fabricaGrupo = new THREE.Group();
const corpoFabrica = new THREE.Mesh(new THREE.BoxGeometry(5, 3, 4), new THREE.MeshStandardMaterial({ color: 0x8d8d8d, roughness: 0.8 }));
corpoFabrica.position.set(0, 1.5, 0);
fabricaGrupo.add(corpoFabrica);
const chamine = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.45, 4, 10), new THREE.MeshStandardMaterial({ color: 0x707070 }));
chamine.position.set(1.6, 4.5, 0);
fabricaGrupo.add(chamine);
fabricaGrupo.position.set(-13, 0, 11);
scene.add(fabricaGrupo);

// Tubulação doméstica (esgoto residencial) + casas
const tuboDomGeo = new THREE.CylinderGeometry(0.22, 0.22, 2.0, 12);
const tuboDom = new THREE.Mesh(tuboDomGeo, tuboMat);
tuboDom.rotation.z = Math.PI / 2;
tuboDom.position.set(12, 0.35, 5.6);
scene.add(tuboDom);

const casasGrupo = new THREE.Group();
const posicoesCasas = [[8, 10], [12, 12], [16, 10.5], [19, 12.5], [10, 13.5]];
for (const [cx, cz] of posicoesCasas) {
  const casa = new THREE.Group();
  const corpo = new THREE.Mesh(new THREE.BoxGeometry(1.6, 1.2, 1.6), new THREE.MeshStandardMaterial({ color: 0xe4d7bd, roughness: 0.9 }));
  corpo.position.y = 0.6;
  const telhado = new THREE.Mesh(new THREE.ConeGeometry(1.3, 0.9, 4), new THREE.MeshStandardMaterial({ color: 0xa1503a, roughness: 0.9 }));
  telhado.rotation.y = Math.PI / 4;
  telhado.position.y = 1.6;
  casa.add(corpo, telhado);
  casa.position.set(cx, 0, cz);
  casasGrupo.add(casa);
}
scene.add(casasGrupo);

// Plantação (margem oposta — zona de escoamento superficial)
const plantacaoGrupo = new THREE.Group();
const plantacaoMats = [];
for (let linha = 0; linha < 5; linha++) {
  for (let coluna = 0; coluna < 9; coluna++) {
    const mat = new THREE.MeshStandardMaterial({ color: 0x5fae3d, roughness: 1.0 });
    const bloco = new THREE.Mesh(new THREE.BoxGeometry(2.6, 0.28, 1.5), mat);
    bloco.position.set(-19 + coluna * 4.6, 0.14, -10.5 - linha * 1.7);
    plantacaoGrupo.add(bloco);
    plantacaoMats.push(mat);
  }
}
scene.add(plantacaoGrupo);

// Chuva (índice de escoamento real do balanço hídrico controla contagem/opacidade)
const N_CHUVA = 500;
const chuvaGeo = new THREE.BufferGeometry();
const chuvaPos = new Float32Array(N_CHUVA * 3);
const chuvaVel = new Float32Array(N_CHUVA);
for (let i = 0; i < N_CHUVA; i++) {
  chuvaPos[i*3] = (Math.random() - 0.5) * 70;
  chuvaPos[i*3+1] = Math.random() * 18;
  chuvaPos[i*3+2] = (Math.random() - 0.5) * 38;
  chuvaVel[i] = 0.25 + Math.random() * 0.2;
}
chuvaGeo.setAttribute('position', new THREE.BufferAttribute(chuvaPos, 3));
const chuvaMat = new THREE.PointsMaterial({ color: 0xbfe0f0, size: 0.10, transparent: true, opacity: 0.0, depthWrite: false });
const chuva = new THREE.Points(chuvaGeo, chuvaMat);
scene.add(chuva);

// Lama de escoamento superficial: plantação -> rio (chuva forte + baixo controle de sedimento)
const N_LAMA = 160;
const lamaGeo = new THREE.BufferGeometry();
const lamaPos = new Float32Array(N_LAMA * 3);
const lamaSeed = new Float32Array(N_LAMA);
for (let i = 0; i < N_LAMA; i++) { lamaSeed[i] = Math.random(); }
lamaGeo.setAttribute('position', new THREE.BufferAttribute(lamaPos, 3));
const lamaMat = new THREE.PointsMaterial({ color: 0x5a4527, size: 0.20, transparent: true, opacity: 0.0, depthWrite: false });
const lama = new THREE.Points(lamaGeo, lamaMat);
scene.add(lama);

// Algas (floração por excesso de Nutrientes — eutrofização)
const N_ALGAS = 220;
const algasGeo = new THREE.BufferGeometry();
const algasPos = new Float32Array(N_ALGAS * 3);
for (let i = 0; i < N_ALGAS; i++) {
  algasPos[i*3] = (Math.random() - 0.5) * 62;
  algasPos[i*3+1] = 0.05 + Math.random() * 0.03;
  algasPos[i*3+2] = (Math.random() - 0.5) * (AGUA_LARGURA - 1.5);
}
algasGeo.setAttribute('position', new THREE.BufferAttribute(algasPos, 3));
const algasMat = new THREE.PointsMaterial({ color: 0x6bbf3a, size: 0.55, transparent: true, opacity: 0.0, depthWrite: false });
const algas = new THREE.Points(algasGeo, algasMat);
scene.add(algas);

// Filme de óleo / espuma química (Metais/Tóxicos + severidade orgânica)
const N_OLEO = 140;
const oleoGeo = new THREE.BufferGeometry();
const oleoPos = new Float32Array(N_OLEO * 3);
for (let i = 0; i < N_OLEO; i++) {
  oleoPos[i*3] = (Math.random() - 0.5) * 30 - 8;
  oleoPos[i*3+1] = 0.04;
  oleoPos[i*3+2] = (Math.random() - 0.5) * (AGUA_LARGURA - 2);
}
oleoGeo.setAttribute('position', new THREE.BufferAttribute(oleoPos, 3));
const oleoMat = new THREE.PointsMaterial({ color: 0x2a2a1e, size: 0.4, transparent: true, opacity: 0.0, depthWrite: false });
const oleo = new THREE.Points(oleoGeo, oleoMat);
scene.add(oleo);

// Partículas: despejo poluente (2 tubos -> água)
function criarDespejo(origemX, origemZ) {
  const N = 220;
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(N * 3);
  const seed = new Float32Array(N);
  for (let i = 0; i < N; i++) { seed[i] = Math.random(); }
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const mat = new THREE.PointsMaterial({ color: 0x3a2f22, size: 0.2, transparent: true, opacity: 0.0, depthWrite: false });
  const pontos = new THREE.Points(geo, mat);
  scene.add(pontos);
  return { pontos, geo, mat, seed, origemX, origemZ, N };
}
const despejoIndustrial = criarDespejo(-11, 5.6);
const despejoDomestico = criarDespejo(12, 5.6);

// Bolhas de oxigenação (tratamento/OD saudável)
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

camera.position.set(0, 13.5, 27);
camera.lookAt(0, 0, 0);

// ---------------------------------------------------------------------------
// Câmera interativa: arrastar (girar) e roda do mouse (zoom); em repouso, retoma
// a órbita cinematográfica suave automaticamente após alguns segundos.
// ---------------------------------------------------------------------------
let anguloCam = 0;
let alturaCam = 12.5;
let raioBase = 27.0;
let arrastando = false;
let pointerAnterior = null;
let ultimaInteracao = -999;
const RAIO_MIN = 15, RAIO_MAX = 42;
const ALTURA_MIN = 6, ALTURA_MAX = 20;

canvas.style.cursor = 'grab';
canvas.addEventListener('pointerdown', (e) => {
  arrastando = true;
  pointerAnterior = { x: e.clientX, y: e.clientY };
  canvas.style.cursor = 'grabbing';
  canvas.setPointerCapture(e.pointerId);
});
window.addEventListener('pointerup', () => { arrastando = false; canvas.style.cursor = 'grab'; });
canvas.addEventListener('pointercancel', () => { arrastando = false; canvas.style.cursor = 'grab'; });
canvas.addEventListener('pointermove', (e) => {
  if (!arrastando || !pointerAnterior) return;
  const dx = e.clientX - pointerAnterior.x;
  const dy = e.clientY - pointerAnterior.y;
  pointerAnterior = { x: e.clientX, y: e.clientY };
  anguloCam += dx * 0.006;
  alturaCam = Math.max(ALTURA_MIN, Math.min(ALTURA_MAX, alturaCam - dy * 0.05));
  ultimaInteracao = t;
});
canvas.addEventListener('wheel', (e) => {
  e.preventDefault();
  raioBase = Math.max(RAIO_MIN, Math.min(RAIO_MAX, raioBase + e.deltaY * 0.02));
  ultimaInteracao = t;
}, { passive: false });

// ---------------------------------------------------------------------------
// Estado / animação
// ---------------------------------------------------------------------------
let anoAtual = ANO_MIN;
let tocando = false;
let nivelAguaAlvo = 0;
let escalaAguaAlvo = 1;
let chuvaAtivaAlvo = 0;
let lamaAtivaAlvo = 0;

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
  const solidosNorm = Math.max(0, Math.min(1, linha.solidos_totais_mg_l / 350.0));
  const odNorm = Math.max(0, Math.min(1, linha.od_mg_l / 8.0));
  const bioticoNorm = Math.max(0, Math.min(1, linha.indice_biotico / 100.0));
  const nutrienteNorm = Math.max(0, Math.min(1, (linha.fosforo_mg_l / 1.2 + linha.nitrogenio_mg_l / 12.0) / 2));
  const metaisNorm = Math.max(0, Math.min(1, linha.metais_toxicos_indice / 100.0));
  const vazaoNorm = normalizar(linha.vazao_m3s_medio, FAIXA_VAZAO);
  const escoamentoNorm = normalizar(linha.indice_escoamento_mm, FAIXA_ESCOAMENTO);
  const phDistancia = Math.max(0, Math.min(1, Math.abs(linha.ph - 7.0) / 1.8));

  aguaUniforms.uSeverity.value = severidade;
  aguaUniforms.uTurbidez.value = turbidezNorm;

  // Iluminação: quente/brilhante (limpo) <-> fria/opaca (poluído); mais nublado com chuva forte
  const corSolLimpo = new THREE.Color(0xfff3d6);
  const corSolPoluido = new THREE.Color(0x8fa3ad);
  sol.color.copy(corSolLimpo).lerp(corSolPoluido, Math.max(severidade, escoamentoNorm * 0.5));
  sol.intensity = 1.6 - severidade * 0.9 - escoamentoNorm * 0.3;
  const corFogLimpo = new THREE.Color(0xbfe0f5);
  const corFogPoluido = new THREE.Color(0x7c7566);
  const corFogAtual = corFogLimpo.clone().lerp(corFogPoluido, severidade);
  scene.fog.color.copy(corFogAtual);
  renderer.setClearColor(corFogAtual, 1.0);

  // Despejo das 2 tubulações (indústria + residências): ativo proporcional à severidade
  despejoIndustrial.mat.opacity = 0.55 * severidade;
  despejoDomestico.mat.opacity = 0.5 * severidade;

  // Bolhas de oxigenação: proporcional ao OD real
  bolhasMat.opacity = 0.75 * odNorm;

  // Algas (eutrofização): proporcional a Fósforo+Nitrogênio
  algasMat.opacity = 0.75 * Math.pow(nutrienteNorm, 1.3);

  // Filme de óleo / espuma química: proporcional a Metais/Tóxicos e à severidade orgânica
  oleoMat.opacity = 0.6 * Math.max(metaisNorm, severidade * 0.5);

  // Sedimento no leito: proporcional a Sólidos Totais
  sedimentoLeitoMat.opacity = 0.55 * solidosNorm;

  // Chuva: intensidade real do balanço hídrico do ano/cenário
  chuvaAtivaAlvo = escoamentoNorm;

  // Lama de escoamento superficial: só aparece com chuva forte E turbidez alta (baixo controle)
  lamaAtivaAlvo = escoamentoNorm > 0.35 && turbidezNorm > 0.35 ? Math.min(escoamentoNorm, turbidezNorm) : 0;

  // Nível d'água e canal: cai e estreita quando a vazão fica abaixo do necessário
  nivelAguaAlvo = -0.55 * (1 - vazaoNorm);
  escalaAguaAlvo = 0.62 + 0.38 * vazaoNorm;
  bancosAreia.forEach((b) => { b.visible = vazaoNorm < 0.45; });

  // Vegetação: verde viçoso <-> seco/acastanhado (severidade + pH fora da faixa neutra)
  const corVegVivo = new THREE.Color(0x4a8a3a);
  const corVegSeca = new THREE.Color(0x6b5a34);
  const murchamento = Math.min(1, severidade * 0.7 + phDistancia * 0.5);
  vegetacao.forEach((v) => {
    v.material.color.copy(corVegVivo).lerp(corVegSeca, murchamento);
    v.scale.y = 0.7 + bioticoNorm * 0.5;
  });

  // Plantação: viçosa quando bem cuidada; some de vigor visual se o solo já está exaurido (proxy: metais/solidos)
  const corPlantaViva = new THREE.Color(0x5fae3d);
  const corPlantaFraca = new THREE.Color(0x8a8a4a);
  plantacaoMats.forEach((m) => m.color.copy(corPlantaViva).lerp(corPlantaFraca, metaisNorm * 0.5));

  // Peixes: vivos/ativos conforme índice biótico; boiam de barriga p/ cima se OD crítico
  const odCritico = linha.od_mg_l < 2.0;
  peixes.forEach((p) => {
    p.visible = bioticoNorm > 0.08 || odCritico;
    p.userData.morto = odCritico;
    p.userData.profAlvo = odCritico ? -0.02 : (-0.4 - (1 - bioticoNorm) * 1.6);
  });

  document.querySelector('#painel .ano').textContent = TEXTOS.ano + " " + ano;
  document.querySelector('#painel .fase').textContent = fase(linha.iqa, linhaAnterior ? linhaAnterior.iqa : null)
    + (usarNaoControlado ? ("  ·  " + TEXTOS.cenario_nao_controlado) : ("  ·  " + TEXTOS.cenario_controlado));
  document.getElementById('metricas').innerHTML = [
    metricaLinha(TEXTOS.metrica_iqa, linha.iqa.toFixed(0)),
    metricaLinha(TEXTOS.metrica_od, linha.od_mg_l.toFixed(2), "mg/L"),
    metricaLinha(TEXTOS.metrica_dbo, linha.dbo_mg_l.toFixed(1), "mg/L"),
    metricaLinha(TEXTOS.metrica_turbidez, linha.turbidez_ntu.toFixed(0), "NTU"),
    metricaLinha(TEXTOS.metrica_vazao, linha.vazao_m3s_medio.toFixed(1), "m³/s"),
    metricaLinha(TEXTOS.metrica_ecoli, Math.round(linha.e_coli_nmp_100ml).toLocaleString('pt-BR'), "NMP/100mL"),
    metricaLinha(TEXTOS.metrica_biotico, linha.indice_biotico.toFixed(0)),
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
  e.target.title = tocando ? TEXTOS.botao_pausar : TEXTOS.botao_reproduzir;
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

function animarDespejo(d, t) {
  const dp = d.geo.attributes.position.array;
  for (let i = 0; i < d.N; i++) {
    const s = d.seed[i];
    const vida = (t * (0.25 + s * 0.3) + s * 10) % 6.0;
    const sinalX = d.origemX < 0 ? 1 : -1;
    dp[i*3] = d.origemX + sinalX * vida * 1.6 + Math.sin(s * 40 + t) * 0.3;
    dp[i*3+1] = 0.3 - vida * 0.06;
    dp[i*3+2] = d.origemZ - vida * 0.4 + Math.sin(s * 20) * vida * 0.5;
  }
  d.geo.attributes.position.needsUpdate = true;
}

let t = 0;
function loop() {
  requestAnimationFrame(loop);
  t += 0.016;
  aguaUniforms.uTime.value = t;

  // câmera: usuário arrasta para girar e usa a roda para zoom; em repouso (>2s sem
  // interação), a órbita cinematográfica automática retoma suavemente (sem saltos,
  // pois o ângulo/altura são acumulados a partir do estado atual, nunca recalculados do zero)
  const inativoPor = t - ultimaInteracao;
  const pesoAutoOrbita = arrastando ? 0 : Math.max(0, Math.min(1, (inativoPor - 2) / 3));
  anguloCam += 0.045 * 0.016 * pesoAutoOrbita;
  const raioCam = raioBase + Math.sin(t * 0.05) * 1.5 * pesoAutoOrbita;
  camera.position.x = Math.sin(anguloCam) * raioCam * 0.5;
  camera.position.z = Math.cos(anguloCam) * raioCam * 0.5 + 7;
  camera.position.y = alturaCam + Math.sin(t * 0.04) * 1.0 * pesoAutoOrbita;
  camera.lookAt(0, -0.3, 0);

  // nível/largura da água transicionam suavemente (evita salto brusco ao trocar de ano)
  // (a água/leito são planos rotacionados -90° em X: a "largura" do rio é o eixo
  // LOCAL Y da geometria, não Z — por isso escalamos scale.y nesses dois; já as
  // partículas de superfície (Points, sem rotação) usam Z como largura de verdade)
  agua.position.y += (nivelAguaAlvo - agua.position.y) * 0.03;
  agua.scale.y += (escalaAguaAlvo - agua.scale.y) * 0.03;
  sedimentoLeito.position.y = agua.position.y - 0.16;
  sedimentoLeito.scale.y = agua.scale.y;
  algas.scale.z = agua.scale.y;
  algas.position.y = agua.position.y;
  oleo.scale.z = agua.scale.y;
  oleo.position.y = agua.position.y;
  bolhas.scale.z = agua.scale.y;
  bolhas.position.y = agua.position.y;

  animarDespejo(despejoIndustrial, t);
  animarDespejo(despejoDomestico, t);

  // bolhas subindo
  const bp = bolhasGeo.attributes.position.array;
  for (let i = 0; i < N_BOLHAS; i++) {
    const s = bolhasSeed[i];
    bp[i*3+1] += 0.01 + s * 0.01;
    if (bp[i*3+1] > 0.6) bp[i*3+1] = -1.6;
  }
  bolhasGeo.attributes.position.needsUpdate = true;

  // algas: leve balanço na superfície
  const ap = algasGeo.attributes.position.array;
  for (let i = 0; i < N_ALGAS; i++) {
    ap[i*3+1] = 0.05 + Math.sin(t * 0.6 + i) * 0.015;
  }
  algasGeo.attributes.position.needsUpdate = true;

  // chuva: caindo continuamente, opacidade/velocidade real via chuvaAtivaAlvo
  chuvaMat.opacity += (chuvaAtivaAlvo * 0.7 - chuvaMat.opacity) * 0.05;
  if (chuvaMat.opacity > 0.02) {
    const cp = chuvaGeo.attributes.position.array;
    for (let i = 0; i < N_CHUVA; i++) {
      cp[i*3+1] -= chuvaVel[i] * (0.5 + chuvaAtivaAlvo);
      if (cp[i*3+1] < 0) cp[i*3+1] = 18;
    }
    chuvaGeo.attributes.position.needsUpdate = true;
  }

  // lama de escoamento: plantação (z negativo) -> borda do rio, ativa com chuva forte + turbidez alta
  lamaMat.opacity += (lamaAtivaAlvo * 0.8 - lamaMat.opacity) * 0.05;
  if (lamaMat.opacity > 0.02) {
    const lp = lamaGeo.attributes.position.array;
    for (let i = 0; i < N_LAMA; i++) {
      const s = lamaSeed[i];
      const vida = (t * (0.3 + s * 0.25) + s * 8) % 5.0;
      lp[i*3] = -18 + s * 36;
      lp[i*3+1] = 0.1;
      lp[i*3+2] = -11 + vida * 0.95;
    }
    lamaGeo.attributes.position.needsUpdate = true;
  }

  // peixes nadando (ou boiando imóveis de barriga p/ cima se a água estiver crítica)
  peixes.forEach((p) => {
    const u = p.userData;
    p.position.y += ((u.profAlvo !== undefined ? u.profAlvo : u.prof) - p.position.y) * 0.02;
    if (u.morto) {
      p.rotation.z += (Math.PI - p.rotation.z) * 0.05;
      u.fase += 0.016 * u.vel * 0.15;
    } else {
      p.rotation.z += (0 - p.rotation.z) * 0.05;
      u.fase += 0.016 * u.vel;
    }
    p.position.x = Math.sin(u.fase) * u.raio;
    p.position.z = Math.cos(u.fase) * u.raio * 0.5;
    p.rotation.y = -u.fase + Math.PI / 2;
  });

  renderer.render(scene, camera);
}

aoRedimensionar();
atualizarParaAno(ANO_MIN);
document.getElementById('carregando').style.display = 'none';
document.getElementById('dicaCamera').style.opacity = '0.85';
loop();
</script>
</body>
</html>
"""


_TEXTOS_PADRAO = {
    "carregando": "Carregando cena…",
    "legenda": "🏭 Indústria &nbsp; 🏘️ Residências &nbsp; 🌾 Plantação &nbsp; 🌧️ Chuva",
    "ver_sem_controle": "ver sem controle",
    "ano": "Ano",
    "cenario_controlado": "cenário controlado",
    "cenario_nao_controlado": "cenário não controlado",
    "fase_agua_limpa": "Água limpa",
    "fase_recuperacao": "Recuperação concluída",
    "fase_tratamento": "Tratamento em ação — recuperando",
    "fase_poluicao": "Poluição avançando",
    "fase_critico": "Estado crítico estável",
    "metrica_iqa": "IQA",
    "metrica_od": "OD",
    "metrica_dbo": "DBO",
    "metrica_turbidez": "Turbidez",
    "metrica_vazao": "Vazão",
    "metrica_ecoli": "E. coli",
    "metrica_biotico": "Índice biótico",
    "botao_reproduzir": "Reproduzir/Pausar",
    "botao_pausar": "Reproduzir/Pausar",
    "dica_camera": "🖱️ arraste para girar · roda para aproximar",
}


def renderizar_html(
    dados_controlado: list[dict],
    dados_nao_controlado: list[dict],
    ano_min: int,
    ano_max: int,
    altura_px: int = 620,
    textos: dict | None = None,
) -> str:
    """Monta o HTML final do componente, injetando as trajetórias reais simuladas (controlado e
    não controlado) — o JS só lê esses dados, nunca gera valores por conta própria.

    `textos` traduz os rótulos exibidos na cena (idiomas suportados por `webapp.i18n`);
    quando omitido, usa os textos em português como padrão."""
    textos_finais = {**_TEXTOS_PADRAO, **(textos or {})}
    payload = {"controlado": dados_controlado, "nao_controlado": dados_nao_controlado}
    html = _TEMPLATE
    html = html.replace("__DADOS_JSON__", json.dumps(payload, ensure_ascii=False))
    html = html.replace("__TEXTOS_JSON__", json.dumps(textos_finais, ensure_ascii=False))
    html = html.replace("__ANO_MIN__", str(ano_min))
    html = html.replace("__ANO_MAX__", str(ano_max))
    html = html.replace("__ALTURA__", str(altura_px))
    html = html.replace("__CARREGANDO__", textos_finais["carregando"])
    html = html.replace("__ANO_LABEL__", textos_finais["ano"])
    html = html.replace("__LEGENDA__", textos_finais["legenda"])
    html = html.replace("__BOTAO_REPRODUZIR__", textos_finais["botao_reproduzir"])
    html = html.replace("__VER_SEM_CONTROLE__", textos_finais["ver_sem_controle"])
    html = html.replace("__DICA_CAMERA__", textos_finais["dica_camera"])
    return html

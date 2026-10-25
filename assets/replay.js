window.dash_clientside = Object.assign({}, window.dash_clientside, {
  nautica: {
    transport: function(tick, play, restart, seek, result, frame, speed) {
      const trigger = window.dash_clientside.callback_context.triggered_id;
      let f = Object.assign({time: 0, playing: false, stamp: Date.now()}, frame || {});
      const end = result.t[result.t.length - 1], now = Date.now();
      if (trigger === 'result' || f.runId !== result.id) {
        f = {time: 0, playing: false, stamp: now, runId: result.id};
      } else if (trigger === 'play') {
        if (f.time >= end) f.time = 0;
        f.playing = !f.playing;
      } else if (trigger === 'restart') {
        f.time = 0; f.playing = false;
      } else if (trigger === 'seek') {
        f.time = Math.max(0, Math.min(end, Number(seek) || 0));
      } else if (trigger === 'ticker' && f.playing) {
        f.time = Math.min(end, f.time + Math.max(0, (now - f.stamp) / 1000) * (speed || 1));
        if (f.time >= end) f.playing = false;
      }
      f.stamp = now;
      const displayedTime = Math.min(end, Math.round(f.time / result.config.dt) * result.config.dt);
      return [f, !f.playing, Number(displayedTime.toFixed(6)), f.playing ? 'Ⅱ Pausar' : '▶ Reproduzir'];
    },
    render: function(frame, r, selected, focus) {
      const i = Math.max(0, Math.min(r.t.length - 1, Math.floor(((frame || {}).time || 0) / r.config.dt + 1e-7)));
      const t = r.t.slice(0, i + 1), end = r.t[r.t.length - 1];
      const focused = (focus || []).includes('focus');
      const names = Object.keys(r.series), active = names.includes(selected) ? selected : names[names.length-1];
      function chart(key, unit, hideBaseline) {
        const visibleNames = names.filter(n => !(hideBaseline && n === 'Sem controle'));
        let maximum = 0.001;
        visibleNames.forEach(n => r.series[n][key].forEach(v => {if (v !== null) maximum = Math.max(maximum, Math.abs(v));}));
        const data = names.filter(n => !(key === 'torque' && n === 'Sem controle')).map(n => ({
          x: t, y: r.series[n][key].slice(0, i + 1), type: 'scatter', mode: 'lines',
          name: n, line: {color: r.series[n].color, width: n === 'Sem controle' ? 1.8 : 2.3,
          dash: n === 'Sem controle' ? 'dot' : 'solid'},
          visible: hideBaseline && n === 'Sem controle' ? 'legendonly' : true,
          hovertemplate: '%{x:.2f} s<br>%{y:.4f} ' + unit + '<extra>' + n + '</extra>'
        }));
        return {data, layout: layout(unit, [-maximum*1.15, maximum*1.15], key)};
      }
      function layout(unit, range, key) {
        return {paper_bgcolor:'#ffffff', plot_bgcolor:'#ffffff', font:{family:'Arial, sans-serif',color:'#505963',size:11},
          margin:{l:62,r:20,t:12,b:45}, height:key==='phi'?300:240,
          xaxis:{title:{text:'Tempo (s)'},range:[0,end],gridcolor:'#e7e8e6',zeroline:false},
          yaxis:{title:{text:unit},range,gridcolor:'#e7e8e6',zerolinecolor:'#b8bdc1',tickformat:'.3~f',automargin:true},
          legend:{orientation:'h',y:1.17,x:0,font:{size:11}}, uirevision:r.id+key+focused,
          shapes:[{type:'line',x0:r.t[i],x1:r.t[i],y0:0,y1:1,yref:'paper',line:{color:'#8b949b',width:1,dash:'dot'}}],
          hovermode:'x unified'};
      }
      let amp = Math.max(.1, ...r.wave.map(Math.abs));
      const wave = {data:[{x:t,y:r.wave.slice(0,i+1),name:'Onda',type:'scatter',mode:'lines',
        line:{color:'#416c8a',width:2}}],layout:layout('°',[-amp*1.15,amp*1.15],'wave')};
      const fmt = (v,d=3) => v===null || v===undefined ? '—' : Number(v).toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
      const s = r.series[active];
      const boats = ['Sem controle','PID','LQR','Fuzzy'];
      const styles = boats.map(n => ({transform:'rotate('+(-(r.series[n]?.phi[i] || 0))+'deg)'}));
      const angles = boats.map(n => r.series[n] ? fmt(r.series[n].phi[i])+'°' : 'Não incluído');
      const cards = boats.map(n => ({opacity:r.series[n]?1:.32}));
      return [chart('phi','°',focused),chart('velocity','°/s',focused),chart('torque','N·m',false),wave,
        fmt(s.phi[i]),fmt(s.velocity[i]),fmt(s.torque[i]),fmt(r.external[i]),
        fmt(r.t[i],2)+' / '+fmt(end,2)+' s', ...styles,...angles,...cards];
    }
  }
});

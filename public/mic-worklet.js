/* Bounded PCM16 packets. AudioWorklet clock is independent of UI rendering. */
class RadioMic extends AudioWorkletProcessor {
  constructor(){super();this.samples=[];this.phase=0;}
  process(inputs){
    const input=inputs[0]?.[0];
    if(!input)return true;
    for(const value of input){
      this.phase+=22050;
      if(this.phase>=sampleRate){this.phase-=sampleRate;this.samples.push(Math.max(-32767,Math.min(32767,Math.round(value*32767))));}
      if(this.samples.length===4096){
        const buffer=new ArrayBuffer(8192), view=new DataView(buffer);
        this.samples.forEach((v,i)=>view.setInt16(i*2,v,true));
        this.port.postMessage(buffer,[buffer]);this.samples=[];
      }
    }
    return true;
  }
}
registerProcessor('radio-mic',RadioMic);

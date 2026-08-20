const TARGET_RATE = 16_000;
const PACKET_SAMPLES = 1_600;

export function float32ToPcm16(samples: Float32Array): Uint8Array {
  const pcm = new Uint8Array(samples.length * 2);
  const view = new DataView(pcm.buffer);
  samples.forEach((sample, index) => {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(index * 2, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
  });
  return pcm;
}

export class PcmPacketizer {
  private source: number[] = [];
  private sourceOffset = 0;
  private output: number[] = [];
  private readonly ratio: number;

  constructor(sourceRate: number) {
    this.ratio = sourceRate / TARGET_RATE;
  }

  push(samples: Float32Array): Uint8Array[] {
    this.source.push(...samples);
    while (this.sourceOffset < this.source.length) {
      this.output.push(this.source[Math.floor(this.sourceOffset)]);
      this.sourceOffset += this.ratio;
    }
    const consumed = Math.min(this.source.length, Math.floor(this.sourceOffset));
    this.source = this.source.slice(consumed);
    this.sourceOffset -= consumed;

    const packets: Uint8Array[] = [];
    while (this.output.length >= PACKET_SAMPLES) {
      packets.push(float32ToPcm16(new Float32Array(this.output.splice(0, PACKET_SAMPLES))));
    }
    return packets;
  }

  flush(): Uint8Array | null {
    if (this.output.length === 0) return null;
    const tail = this.output.splice(0);
    return float32ToPcm16(new Float32Array(tail));
  }
}

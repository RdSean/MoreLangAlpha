import { describe, expect, it } from 'vitest';
import { PcmPacketizer, float32ToPcm16 } from '../voice-input.pcm';

describe('voice input PCM helpers', () => {
  it('converts float samples to little-endian signed PCM16', () => {
    expect(Array.from(float32ToPcm16(new Float32Array([-1, 0, 1])))).toEqual([
      0x00, 0x80, 0x00, 0x00, 0xff, 0x7f,
    ]);
  });

  it('emits 100 ms packets at 16 kHz', () => {
    const packetizer = new PcmPacketizer(16_000);

    const packets = packetizer.push(new Float32Array(1_600));

    expect(packets).toHaveLength(1);
    expect(packets[0]).toHaveLength(3_200);
  });

  it('resamples 48 kHz input before packetizing', () => {
    const packetizer = new PcmPacketizer(48_000);

    const packets = packetizer.push(new Float32Array(4_800));

    expect(packets).toHaveLength(1);
    expect(packets[0]).toHaveLength(3_200);
  });

  it('flushes a final packet shorter than 100 ms', () => {
    const packetizer = new PcmPacketizer(16_000);

    expect(packetizer.push(new Float32Array(800))).toEqual([]);

    expect(packetizer.flush()).toHaveLength(1_600);
  });
});

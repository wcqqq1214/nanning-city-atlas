type Pointer = {
  pointerId: number;
  clientX: number;
  clientY: number;
  button: number;
};

/** A tap must remain a single, stationary primary pointer for its entire lifetime. */
export class TapGesture {
  private active = new Set<number>();
  private candidate: Pointer | null = null;

  start(pointer: Pointer) {
    this.active.add(pointer.pointerId);
    this.candidate =
      this.active.size === 1 && pointer.button === 0
        ? {
            pointerId: pointer.pointerId,
            clientX: pointer.clientX,
            clientY: pointer.clientY,
            button: pointer.button,
          }
        : null;
  }

  move(pointer: Pointer) {
    if (
      this.candidate &&
      Math.hypot(
        pointer.clientX - this.candidate.clientX,
        pointer.clientY - this.candidate.clientY,
      ) > 6
    )
      this.candidate = null;
  }

  end(pointer: Pointer): boolean {
    this.move(pointer);
    this.active.delete(pointer.pointerId);
    const tapped =
      this.active.size === 0 && this.candidate?.pointerId === pointer.pointerId;
    this.candidate = null;
    return tapped;
  }

  cancel(pointer: Pointer) {
    this.active.delete(pointer.pointerId);
    this.candidate = null;
  }
}

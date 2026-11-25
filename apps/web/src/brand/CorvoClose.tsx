import { useEffect, useRef, useState } from "react";

/** The eye's center, in the drawing's own units (viewBox below). */
export const OLHO = { x: 499, y: 365 };
/** Where the pupil rests, a little toward the form, as in the mockup. */
const PUPILA = { x: 503, y: 367 };
/** How far the pupil travels toward a focused field, in screen pixels. */
export const OLHAR_PX = 6;

/** The pupil's offset, in drawing units, from the eye toward the target: `px` screen pixels long,
 * divided by how many screen pixels one drawing unit takes (`scale`). */
export function olhar(olho: { x: number; y: number }, alvo: { x: number; y: number }, scale: number, px = OLHAR_PX) {
  const dx = alvo.x - olho.x;
  const dy = alvo.y - olho.y;
  const length = Math.hypot(dx, dy);
  if (!length || !scale) return { dx: 0, dy: 0 };
  const units = px / scale;
  return { dx: (dx / length) * units, dy: (dy / length) * units };
}

function calmo(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/** The crow in close, from `brand/simbolo/corvo-olho-icone.svg` (the same paths, carried past the
 * bottom and left edges so the head bleeds off the page, as in the login mockup). Flat tinta on
 * papel; the amber eye is the only color. Drawn inline so the pupil can follow `alvo`, the field
 * that has focus, unless the person asked for less motion. */
export function CorvoClose({ alvo, className }: { alvo?: Element | null; className?: string }) {
  const svg = useRef<SVGSVGElement>(null);
  const [desvio, setDesvio] = useState({ dx: 0, dy: 0 });

  useEffect(() => {
    const ctm = svg.current?.getScreenCTM();
    if (!alvo || !ctm || calmo()) {
      setDesvio({ dx: 0, dy: 0 });
      return;
    }
    const rect = alvo.getBoundingClientRect();
    const olho = { x: ctm.a * PUPILA.x + ctm.c * PUPILA.y + ctm.e, y: ctm.b * PUPILA.x + ctm.d * PUPILA.y + ctm.f };
    setDesvio(olhar(olho, { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }, ctm.a));
  }, [alvo]);

  return (
    <svg
      ref={svg}
      className={className}
      viewBox="380 150 470 557"
      preserveAspectRatio="xMaxYMid slice"
      role="img"
      aria-label="O corvo do VISAO, de olho âmbar"
    >
      <rect x="380" y="150" width="470" height="557" fill="#F3F1EC" />
      <path fill="#101214" d="M608.3 706.8 L585.7 657.5 L585.5 655.1 L586.6 651.0 L580.2 635.4 L576.0 622.0 L573.5 610.1 L571.9 593.9 L572.4 591.6 L574.6 588.3 L575.2 578.8 L579.3 574.3 L583.9 549.1 L590.3 528.2 L593.1 520.5 L596.5 517.5 L598.6 512.4 L602.1 509.2 L603.1 500.4 L604.1 498.3 L606.2 495.9 L606.7 491.4 L607.6 489.2 L611.0 486.3 L614.5 479.6 L620.4 471.6 L626.1 465.9 L632.4 460.7 L640.9 455.0 L651.3 449.2 L676.6 438.3 L700.7 435.3 L726.2 430.4 L745.7 425.6 L780.1 415.2 L792.0 412.7 L800.0 412.1 L807.4 412.7 L813.4 415.1 L820.7 419.1 L822.8 419.1 L823.9 417.9 L824.0 416.0 L819.4 402.9 L814.6 392.2 L807.4 380.6 L798.4 369.5 L786.8 358.4 L774.1 348.6 L758.7 339.4 L746.1 333.2 L734.8 329.0 L720.4 325.0 L716.4 321.5 L706.6 319.0 L688.9 316.0 L667.0 314.2 L632.8 313.5 L591.0 313.7 L588.5 312.7 L562.1 295.6 L544.9 286.7 L539.6 286.7 L522.9 282.2 L508.2 279.0 L503.6 280.3 L485.5 279.1 L468.7 278.8 L463.9 281.4 L436.6 284.9 L428.7 286.6 L424.9 289.8 L410.1 294.8 L396.7 300.4 L393.4 305.0 L380.0 313.9 L380.0 707.0 L608.3 706.8Z" />
      <path fill="#F3F1EC" fillRule="evenodd" d="M472.4 289.8 L454.3 291.0 L436.6 294.2 L444.1 295.3 L432.0 297.8 L422.8 300.6 L431.1 301.2 L411.8 306.5 L397.1 312.9 L388.3 317.8 L380.0 323.3 L380.0 337.5 L395.5 325.3 L404.0 320.0 L412.9 315.2 L422.1 311.3 L429.7 308.9 L445.4 305.9 L467.4 304.6 L493.3 305.4 L463.4 308.2 L439.8 312.6 L428.3 316.2 L415.2 321.2 L406.2 325.6 L395.8 331.6 L413.7 325.1 L427.2 321.2 L441.5 318.5 L455.3 317.4 L469.3 317.5 L486.4 318.6 L478.7 319.9 L468.9 322.7 L459.3 326.4 L450.6 330.7 L468.2 327.5 L484.1 326.2 L506.2 326.5 L533.1 328.5 L507.1 318.2 L497.4 315.3 L483.6 312.3 L497.6 313.0 L519.4 316.1 L533.2 318.6 L548.3 322.5 L534.0 315.4 L522.9 310.7 L513.5 307.4 L501.9 304.3 L515.8 305.8 L529.4 308.9 L542.9 312.8 L558.0 318.4 L532.8 304.1 L574.3 313.7 L554.2 300.7 L543.7 294.8 L548.8 299.1 L532.2 292.6 L520.4 288.8 L527.7 293.4 L510.1 289.4 L496.2 287.6 L476.2 287.1 L484.3 289.8 L472.4 289.8Z M489.0 500.5 L511.1 485.9 L525.6 466.2 L488.8 498.5 L487.3 499.9 L487.1 501.2 L489.0 500.5Z M404.1 432.3 L380.0 470.0 L380.0 478.2 L408.1 426.9 L404.1 432.3Z M412.6 462.0 L387.4 505.8 L384.0 513.1 L380.0 525.6 L380.0 540.2 L412.6 462.0Z M428.9 481.0 L383.7 587.0 L380.0 596.1 L380.0 597.4 L408.5 546.8 L419.7 512.0 L428.9 481.0Z M442.1 524.4 L421.5 573.0 L406.4 630.0 L416.0 607.7 L442.1 524.4Z M455.8 552.0 L447.3 593.7 L434.8 659.4 L436.6 655.0 L450.4 610.5 L455.0 564.1 L455.8 552.0Z M479.0 575.1 L471.2 629.1 L465.2 699.2 L469.3 683.6 L474.5 659.9 L479.0 575.1Z M494.7 601.3 L495.6 645.9 L502.2 707.0 L504.5 707.0 L504.9 679.4 L504.5 663.2 L494.7 601.3Z M380.0 655.5 L396.8 668.3 L408.4 679.6 L418.4 692.1 L426.6 705.5 L426.2 702.9 L422.9 693.0 L431.6 707.0 L446.9 707.0 L437.3 690.1 L419.9 668.2 L400.0 648.4 L380.0 631.2 L380.0 632.3 L386.7 640.7 L380.0 636.3 L380.0 655.5Z M632.2 322.4 L612.7 325.7 L594.0 330.3 L636.1 330.1 L654.1 330.8 L668.0 332.2 L668.8 332.6 L654.9 333.9 L637.2 337.6 L623.6 341.0 L611.2 344.9 L631.0 342.4 L649.2 342.5 L678.8 347.2 L696.5 351.0 L706.9 353.8 L681.1 350.2 L663.1 349.1 L653.1 349.5 L617.5 352.6 L653.2 357.6 L692.8 364.0 L692.2 364.4 L664.2 363.5 L646.1 364.7 L658.7 367.2 L642.8 369.1 L612.8 373.9 L605.3 375.9 L614.1 376.4 L565.2 388.3 L561.8 389.7 L560.5 390.9 L543.4 411.0 L543.8 411.2 L560.0 404.2 L571.6 400.3 L587.7 395.8 L605.1 392.2 L652.6 384.2 L682.2 380.3 L712.1 377.5 L736.1 376.8 L748.2 377.3 L760.1 378.7 L767.9 380.7 L775.3 383.7 L784.2 388.4 L795.8 396.2 L805.1 403.9 L815.2 413.6 L815.5 413.1 L810.3 400.0 L805.6 391.1 L799.9 382.9 L792.0 374.0 L781.6 364.6 L770.3 356.2 L756.9 347.6 L744.4 340.9 L731.3 335.0 L718.4 331.7 L714.3 329.3 L698.9 326.0 L678.9 323.8 L652.7 323.0 L650.4 322.4 L658.5 320.8 L648.4 320.8 L632.2 322.4Z M606.6 405.5 L622.7 400.2 L632.5 397.8 L660.4 393.7 L698.6 390.6 L718.8 389.7 L732.9 389.8 L758.9 391.5 L776.9 394.7 L790.3 399.4 L806.3 408.4 L800.0 403.0 L791.3 397.0 L782.8 392.4 L774.1 389.0 L766.7 387.0 L756.4 385.2 L731.9 383.5 L709.7 383.6 L685.6 385.0 L659.5 388.0 L625.6 392.8 L615.7 394.8 L606.6 405.5Z M565.4 411.9 L565.2 411.4 L565.9 411.0 L565.2 410.5 L573.2 409.2 L599.6 407.1 L601.1 406.2 L604.9 401.3 L610.6 395.4 L585.0 400.4 L573.1 403.3 L557.6 408.4 L544.6 414.3 L548.7 413.9 L556.6 411.8 L565.4 411.9Z M492.6 536.6 L526.2 495.8 L541.3 476.5 L517.0 499.1 L497.8 527.8 L492.6 536.6Z M511.8 556.3 L541.8 507.8 L556.5 488.3 L547.4 496.0 L531.2 511.5 L511.8 556.3Z M528.9 571.3 L557.9 517.4 L570.9 491.3 L552.5 510.7 L550.4 513.8 L539.7 540.5 L528.9 571.3Z M550.3 555.5 L549.2 584.9 L559.8 548.1 L566.5 529.2 L568.5 525.6 L565.7 539.1 L565.0 549.4 L565.8 561.2 L568.3 574.3 L570.8 558.4 L576.7 535.0 L580.3 523.5 L587.1 506.6 L587.5 504.4 L569.2 524.0 L580.6 500.4 L585.3 489.3 L574.7 505.2 L566.5 519.0 L559.9 531.5 L553.2 546.2 L552.7 540.1 L551.1 547.5 L550.3 555.5Z M539.3 609.7 L546.0 656.1 L552.5 677.0 L560.6 707.0 L563.8 707.0 L558.9 673.2 L551.4 639.7 L548.9 632.0 L539.3 609.7Z M540.6 707.0 L536.1 677.3 L530.5 653.5 L520.1 603.9 L522.0 628.2 L524.9 654.4 L536.9 707.0 L540.6 707.0Z M570.3 677.8 L580.0 707.0 L598.2 707.0 L571.0 646.6 L580.1 659.2 L570.5 632.7 L566.4 619.3 L563.0 603.6 L560.9 586.6 L559.8 622.7 L560.7 642.8 L562.9 656.6 L571.3 693.8 L570.3 677.8Z" />
      <circle cx={OLHO.x} cy={OLHO.y} r="27" fill="#101214" />
      <circle cx={OLHO.x} cy={OLHO.y} r="22" fill="#E39A2E" />
      <circle
        className="corvo-close-pupila"
        cx={PUPILA.x}
        cy={PUPILA.y}
        r="9.5"
        fill="#101214"
        style={{ transform: `translate(${desvio.dx}px, ${desvio.dy}px)` }}
      />
      <circle cx="492" cy="357" r="4" fill="#F3F1EC" />
    </svg>
  );
}

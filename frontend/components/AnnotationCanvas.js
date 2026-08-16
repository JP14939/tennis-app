import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react';
import { View, PanResponder, StyleSheet } from 'react-native';
import Svg, { Path, Line, Circle, G } from 'react-native-svg';

// Telestrator-style freehand drawing layer for one video pane. Strokes live
// in this component's own state and reset on unmount by default -- this
// component itself still has no storage/network code. SyncCompareScreen
// opts into persistence explicitly via getStrokes()/loadStrokes(), saving
// through a separate API call rather than this component knowing about it.
//
// `active` gates BOTH the responder's start/move handlers AND pointerEvents
// on the wrapping View -- pointerEvents='none' means RN doesn't even
// dispatch touch events to this layer at all when inactive, so it can sit
// on top of the video without ever stealing a touch meant for something
// else (the scrubber, the ScrollView) while annotate mode is off.
//
// tool/color/active are read from refs inside the PanResponder callbacks,
// not closed over directly -- PanResponder.create() only runs once (inside
// the outer useRef), so a callback that closed over these props directly
// would keep using whatever they were on first render. Mirrors the fix
// needed for any changing value read inside a ref-memoized PanResponder.
function arrowHead(x2, y2, angle, color) {
  const headLen = 12;
  const a1 = angle + Math.PI - Math.PI / 7;
  const a2 = angle + Math.PI + Math.PI / 7;
  const p1 = { x: x2 + headLen * Math.cos(a1), y: y2 + headLen * Math.sin(a1) };
  const p2 = { x: x2 + headLen * Math.cos(a2), y: y2 + headLen * Math.sin(a2) };
  return (
    <>
      <Line x1={x2} y1={y2} x2={p1.x} y2={p1.y} stroke={color} strokeWidth={3} strokeLinecap="round" />
      <Line x1={x2} y1={y2} x2={p2.x} y2={p2.y} stroke={color} strokeWidth={3} strokeLinecap="round" />
    </>
  );
}

function renderStroke(st, key) {
  if (st.tool === 'pen') {
    if (st.points.length < 2) return null;
    const d = st.points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');
    return <Path key={key} d={d} stroke={st.color} strokeWidth={3} fill="none" strokeLinecap="round" strokeLinejoin="round" />;
  }
  if (st.tool === 'line' || st.tool === 'arrow') {
    const angle = Math.atan2(st.y2 - st.y1, st.x2 - st.x1);
    return (
      <G key={key}>
        <Line x1={st.x1} y1={st.y1} x2={st.x2} y2={st.y2} stroke={st.color} strokeWidth={3} strokeLinecap="round" />
        {st.tool === 'arrow' && arrowHead(st.x2, st.y2, angle, st.color)}
      </G>
    );
  }
  if (st.tool === 'circle') {
    const cx = (st.x1 + st.x2) / 2;
    const cy = (st.y1 + st.y2) / 2;
    const r = Math.hypot(st.x2 - st.x1, st.y2 - st.y1) / 2;
    return <Circle key={key} cx={cx} cy={cy} r={r} stroke={st.color} strokeWidth={3} fill="none" />;
  }
  return null;
}

const AnnotationCanvas = forwardRef(function AnnotationCanvas({ width, height, tool, color, active }, ref) {
  const [strokes, setStrokes] = useState([]);
  const [current, setCurrent] = useState(null);

  const toolRef = useRef(tool);
  const colorRef = useRef(color);
  const activeRef = useRef(active);
  useEffect(() => { toolRef.current = tool; }, [tool]);
  useEffect(() => { colorRef.current = color; }, [color]);
  useEffect(() => { activeRef.current = active; }, [active]);

  useImperativeHandle(ref, () => ({
    clear: () => { setStrokes([]); setCurrent(null); },
    undo: () => setStrokes((prev) => prev.slice(0, -1)),
    // Raw pane-local pixel coordinates -- meaningless without the width/height
    // they were captured at, which the caller already has (same width/height
    // props passed to this component) since panes are a fixed size per screen.
    getStrokes: () => strokes,
    loadStrokes: (loaded) => { setStrokes(Array.isArray(loaded) ? loaded : []); setCurrent(null); },
  }));

  const responder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => activeRef.current,
      onMoveShouldSetPanResponder: () => activeRef.current,
      onPanResponderGrant: (evt) => {
        if (!activeRef.current) return;
        const { locationX: x, locationY: y } = evt.nativeEvent;
        const t = toolRef.current;
        const c = colorRef.current;
        setCurrent(t === 'pen'
          ? { tool: t, color: c, points: [{ x, y }] }
          : { tool: t, color: c, x1: x, y1: y, x2: x, y2: y });
      },
      onPanResponderMove: (evt) => {
        if (!activeRef.current) return;
        const { locationX: x, locationY: y } = evt.nativeEvent;
        setCurrent((prev) => {
          if (!prev) return prev;
          if (prev.tool === 'pen') return { ...prev, points: [...prev.points, { x, y }] };
          return { ...prev, x2: x, y2: y };
        });
      },
      onPanResponderRelease: () => {
        setCurrent((prev) => {
          if (prev) setStrokes((s) => [...s, prev]);
          return null;
        });
      },
      onPanResponderTerminate: () => setCurrent(null),
    })
  ).current;

  if (!width || !height) return null;

  return (
    <View
      style={[StyleSheet.absoluteFill, { width, height }]}
      pointerEvents={active ? 'auto' : 'none'}
      {...responder.panHandlers}
    >
      <Svg width={width} height={height} style={StyleSheet.absoluteFill}>
        {strokes.map((st, i) => renderStroke(st, i))}
        {current && renderStroke(current, 'current')}
      </Svg>
    </View>
  );
});

export default AnnotationCanvas;

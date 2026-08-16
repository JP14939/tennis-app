import { useEffect, useState } from 'react';
import { Dimensions } from 'react-native';

// Same state+listener pattern already used locally in ContactMarkingScreen.js
// (useDims()) -- pulled out here so every screen that needs to recompute a
// layout dimension on rotation/different Android screen sizes shares one
// implementation instead of each hardcoding Dimensions.get('window') once at
// module load (which never updates after the first render).
export function useWindowWidth() {
  const [width, setWidth] = useState(Dimensions.get('window').width);
  useEffect(() => {
    const sub = Dimensions.addEventListener('change', ({ window }) => setWidth(window.width));
    return () => sub?.remove();
  }, []);
  return width;
}

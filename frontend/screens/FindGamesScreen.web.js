import { View, Text, StyleSheet, SafeAreaView } from 'react-native';
import { colors, fonts, radius, spacing } from '../theme';
import { MapPinIcon } from '../components/icons';

// react-native-maps has no web implementation -- even a runtime
// Platform.OS check inside FindGamesScreen.js couldn't keep it out of the
// web bundle, since Metro resolves every require()'d module into the
// bundle graph at build time regardless of whether the branch is actually
// reached at runtime (that's what broke `npx expo start` + `w`: the whole
// app failed to bundle, not just this screen). Splitting into .native.js /
// .web.js files uses Metro's platform-extension resolution instead, which
// excludes the native file from the web bundle entirely -- same pattern as
// components/PlatformVideo.native.js / .web.js elsewhere in this app.
export default function FindGamesScreen() {
  return (
    <SafeAreaView style={s.safe}>
      <View style={s.centerFill}>
        <MapPinIcon size={32} color={colors.muted} />
        <Text style={s.webFallbackTitle}>Find Games</Text>
        <Text style={s.webFallbackSub}>The court map isn't available on web yet — open RallyMax on your phone to browse and post availability at courts near you.</Text>
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 32 },
  webFallbackTitle: { color: colors.ink, fontSize: 20, fontFamily: fonts.bold, marginTop: 14 },
  webFallbackSub: { color: colors.muted, fontSize: 13, textAlign: 'center', marginTop: 8, lineHeight: 19, fontFamily: fonts.regular },
});

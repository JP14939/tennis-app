import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView } from 'react-native';

const GREEN  = '#4ade80';
const DARK   = '#0d0d0d';
const CARD   = '#141414';
const BORDER = '#222';
const TEXT   = '#fff';
const MUTED  = '#888';

function FeatureCard({ icon, title, desc, cta, onPress }) {
  return (
    <View style={c.card}>
      <View style={c.iconWrap}>
        <Text style={c.icon}>{icon}</Text>
      </View>
      <Text style={c.title}>{title}</Text>
      <Text style={c.desc}>{desc}</Text>
      <TouchableOpacity style={c.btn} onPress={onPress} activeOpacity={0.85}>
        <Text style={c.btnText}>{cta}</Text>
      </TouchableOpacity>
    </View>
  );
}
const c = StyleSheet.create({
  card: {
    backgroundColor: CARD, borderWidth: 1, borderColor: BORDER,
    borderRadius: 18, padding: 20, marginBottom: 16,
  },
  iconWrap: {
    width: 44, height: 44, borderRadius: 12, backgroundColor: '#1a2e1a',
    alignItems: 'center', justifyContent: 'center', marginBottom: 14,
  },
  icon: { fontSize: 22 },
  title: { color: TEXT, fontSize: 17, fontWeight: '800', marginBottom: 6 },
  desc: { color: MUTED, fontSize: 13, lineHeight: 19, marginBottom: 16 },
  btn: { backgroundColor: GREEN, borderRadius: 12, paddingVertical: 13, alignItems: 'center' },
  btnText: { color: '#000', fontSize: 14, fontWeight: '700' },
});

export default function PremiumScreen({ navigation }) {
  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>

        <View style={s.badge}>
          <Text style={s.badgeText}>✨ PREMIUM</Text>
        </View>
        <Text style={s.title}>Go deeper on your game</Text>
        <Text style={s.sub}>Two ways to get more out of your footage.</Text>

        <FeatureCard
          icon="🥊"
          title="1v1 Comparison"
          desc="Upload any video you want to copy — a pro clip, a friend, yourself last year — and compare your swing directly against it, frame for frame."
          cta="Compare videos →"
          onPress={() => navigation.navigate('VersusPick')}
        />

        <FeatureCard
          icon="🎬"
          title="Highlight Archive"
          desc="Upload a full match and we'll automatically clip every shot into your personal swing archive, ready to tag and analyse."
          cta="Upload a match →"
          onPress={() => navigation.navigate('HighlightUpload')}
        />

      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: DARK },
  scroll: { padding: 20, paddingTop: 16, paddingBottom: 40 },

  badge: {
    alignSelf: 'flex-start', backgroundColor: '#1a2e1a', borderWidth: 1, borderColor: '#2a4a2a',
    borderRadius: 20, paddingHorizontal: 12, paddingVertical: 5, marginBottom: 14,
  },
  badgeText: { color: GREEN, fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },

  title: { color: TEXT, fontSize: 24, fontWeight: '800', letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: MUTED, fontSize: 14, marginBottom: 24 },
});

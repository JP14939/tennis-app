import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { useAuth } from '../context/AuthContext';

export default function SignupScreen({ navigation }) {
  const { signup } = useAuth();
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleSignup() {
    setError('');
    if (!name || !email || !password) {
      setError('Please fill in all fields.');
      return;
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    setLoading(true);
    try {
      await signup(email, password, name);
      navigation.navigate('MainTabs', { screen: 'Home' });
    } catch (err) {
      setError(err.message || 'Something went wrong');
    } finally {
      setLoading(false);
    }
  }

  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={s.flex}>
        <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">

          <View style={s.header}>
            <Text style={s.logo}>🎾</Text>
            <Text style={s.title}>Create account</Text>
            <Text style={s.sub}>Start analysing your swing for free</Text>
          </View>

          <View style={s.perks}>
            {['2 free swing analyses per day', 'Matched to pro players', 'Personalised coaching tips'].map(p => (
              <View key={p} style={s.perk}>
                <Text style={s.perkCheck}>✓</Text>
                <Text style={s.perkText}>{p}</Text>
              </View>
            ))}
          </View>

          <View style={s.form}>
            <View style={s.field}>
              <Text style={s.label}>Full name</Text>
              <TextInput
                style={s.input}
                placeholder="Roger Federer"
                placeholderTextColor="#555"
                autoCapitalize="words"
                autoComplete="name"
                value={name}
                onChangeText={setName}
              />
            </View>

            <View style={s.field}>
              <Text style={s.label}>Email</Text>
              <TextInput
                style={s.input}
                placeholder="you@example.com"
                placeholderTextColor="#555"
                keyboardType="email-address"
                autoCapitalize="none"
                autoComplete="email"
                value={email}
                onChangeText={setEmail}
              />
            </View>

            <View style={s.field}>
              <Text style={s.label}>Password</Text>
              <TextInput
                style={s.input}
                placeholder="Min. 8 characters"
                placeholderTextColor="#555"
                secureTextEntry
                autoComplete="new-password"
                value={password}
                onChangeText={setPassword}
              />
            </View>

            {error ? <Text style={s.error}>{error}</Text> : null}

            <TouchableOpacity
              style={[s.btnPrimary, loading && s.btnDisabled]}
              onPress={handleSignup}
              disabled={loading}
            >
              <Text style={s.btnPrimaryText}>{loading ? 'Creating account...' : 'Create free account'}</Text>
            </TouchableOpacity>

            <Text style={s.terms}>
              By signing up you agree to our Terms of Service and Privacy Policy.
            </Text>
          </View>

          <View style={s.footer}>
            <Text style={s.footerText}>Already have an account? </Text>
            <TouchableOpacity onPress={() => navigation.navigate('Login')}>
              <Text style={s.footerLink}>Log in</Text>
            </TouchableOpacity>
          </View>

        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0d0d0d' },
  flex: { flex: 1 },
  scroll: { flexGrow: 1, padding: 24 },

  header: { alignItems: 'center', marginBottom: 24 },
  logo: { fontSize: 40, marginBottom: 14 },
  title: { color: '#fff', fontSize: 26, fontWeight: '700', letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: '#666', fontSize: 15 },

  perks: {
    backgroundColor: '#111',
    borderWidth: 1,
    borderColor: '#1e2e1e',
    borderRadius: 12,
    padding: 16,
    gap: 10,
    marginBottom: 28,
  },
  perk: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  perkCheck: { color: '#4ade80', fontWeight: '700', fontSize: 15 },
  perkText: { color: '#aaa', fontSize: 14 },

  form: { gap: 16 },
  field: { gap: 6 },
  label: { color: '#aaa', fontSize: 13, fontWeight: '500' },
  input: {
    backgroundColor: '#1a1a1a',
    borderWidth: 1,
    borderColor: '#2a2a2a',
    borderRadius: 10,
    padding: 14,
    color: '#fff',
    fontSize: 15,
  },

  error: { color: '#f87171', fontSize: 13, textAlign: 'center' },

  btnPrimary: {
    backgroundColor: '#4ade80',
    borderRadius: 12,
    padding: 15,
    alignItems: 'center',
    marginTop: 4,
  },
  btnDisabled: { opacity: 0.6 },
  btnPrimaryText: { color: '#000', fontSize: 16, fontWeight: '700' },

  terms: { color: '#444', fontSize: 11, textAlign: 'center', lineHeight: 16 },

  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 32,
  },
  footerText: { color: '#555', fontSize: 14 },
  footerLink: { color: '#4ade80', fontSize: 14, fontWeight: '600' },
});

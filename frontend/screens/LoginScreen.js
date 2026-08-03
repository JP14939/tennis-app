import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity,
  StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { useAuth } from '../context/AuthContext';

export default function LoginScreen({ navigation }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleLogin() {
    setError('');
    if (!email || !password) {
      setError('Please fill in all fields.');
      return;
    }
    setLoading(true);
    try {
      await login(email, password);
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
            <Text style={s.title}>Welcome back</Text>
            <Text style={s.sub}>Log in to your TennisAI account</Text>
          </View>

          <View style={s.form}>
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
                placeholder="••••••••"
                placeholderTextColor="#555"
                secureTextEntry
                autoComplete="password"
                value={password}
                onChangeText={setPassword}
              />
            </View>

            {error ? <Text style={s.error}>{error}</Text> : null}

            <TouchableOpacity
              style={[s.btnPrimary, loading && s.btnDisabled]}
              onPress={handleLogin}
              disabled={loading}
            >
              <Text style={s.btnPrimaryText}>{loading ? 'Logging in...' : 'Log in'}</Text>
            </TouchableOpacity>

            <TouchableOpacity style={s.forgotWrap}>
              <Text style={s.forgot}>Forgot password?</Text>
            </TouchableOpacity>
          </View>

          <View style={s.footer}>
            <Text style={s.footerText}>Don't have an account? </Text>
            <TouchableOpacity onPress={() => navigation.navigate('Signup')}>
              <Text style={s.footerLink}>Sign up free</Text>
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

  header: { alignItems: 'center', marginBottom: 40 },
  logo: { fontSize: 40, marginBottom: 14 },
  title: { color: '#fff', fontSize: 26, fontWeight: '700', letterSpacing: -0.5, marginBottom: 6 },
  sub: { color: '#666', fontSize: 15 },

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

  forgotWrap: { alignItems: 'center', marginTop: 4 },
  forgot: { color: '#555', fontSize: 13 },

  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    marginTop: 40,
  },
  footerText: { color: '#555', fontSize: 14 },
  footerLink: { color: '#4ade80', fontSize: 14, fontWeight: '600' },
});

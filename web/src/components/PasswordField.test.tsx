import { createRef, type FormEvent, type ReactElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ThemeProvider } from '@mui/material/styles';
import { PasswordField } from '@/components/PasswordField';
import { theme } from '@/theme';

function renderWithTheme(ui: ReactElement) {
  return render(<ThemeProvider theme={theme}>{ui}</ThemeProvider>);
}

function LoginPasswordForm({
  onValid,
}: {
  onValid: (values: { email: string; password: string }) => void;
}) {
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    onValid({
      email: String(data.get('email') ?? ''),
      password: String(data.get('password') ?? ''),
    });
  };
  return (
    <form onSubmit={submit} noValidate>
      <input aria-label="Email" name="email" defaultValue="demo@bizboard.local" />
      <PasswordField name="password" label="Password" />
      <button type="submit">Sign in</button>
    </form>
  );
}

describe('PasswordField', () => {
  it('forwards the ref to the native input so react-hook-form can read the value', () => {
    const ref = createRef<HTMLInputElement>();
    renderWithTheme(<PasswordField label="Password" ref={ref} />);
    expect(ref.current).toBeInstanceOf(HTMLInputElement);
    expect(ref.current).toHaveAttribute('type', 'password');
  });

  it('does not submit the surrounding form when the visibility toggle is clicked', async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn((event: { preventDefault: () => void }) => event.preventDefault());
    renderWithTheme(
      <form onSubmit={onSubmit}>
        <PasswordField label="Password" />
        <button type="submit">Save</button>
      </form>,
    );

    await user.click(screen.getByRole('button', { name: 'Show password' }));

    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: 'Hide password' })).toBeInTheDocument();
  });

  it('includes the typed password in form data', async () => {
    const user = userEvent.setup();
    const onValid = vi.fn();
    renderWithTheme(<LoginPasswordForm onValid={onValid} />);

    await user.type(screen.getByLabelText('Password'), 'DemoPass123!');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(onValid).toHaveBeenCalledWith({
      email: 'demo@bizboard.local',
      password: 'DemoPass123!',
    });
  });

  it('includes a browser-autofilled password that never fired React onChange', async () => {
    const user = userEvent.setup();
    const onValid = vi.fn();
    renderWithTheme(<LoginPasswordForm onValid={onValid} />);

    const input = screen.getByLabelText('Password') as HTMLInputElement;
    input.value = 'DemoPass123!';
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    expect(onValid).toHaveBeenCalledWith({
      email: 'demo@bizboard.local',
      password: 'DemoPass123!',
    });
  });
});

import { describe, expect, it } from 'vitest';
import { extraValuesFromProducts, parseCfSearchParams } from '@/hooks/useCfFilters';
import { fieldDefRowErrors, fieldDefsHaveErrors } from '@/pages/inventory/itemCustomFieldDefaults';

describe('fieldDefRowErrors', () => {
  it('flags key format, unique keys/labels, and list options', () => {
    const errors = fieldDefRowErrors([
      { key: '1bad', label: 'A', type: 'text', active: true },
      { key: 'color', label: 'Color', type: 'text', active: true },
      { key: 'color', label: 'Shade', type: 'text', active: true },
      { key: 'form', label: 'Form', type: 'list', active: true, options: [] },
    ]);
    expect(errors[0].key).toBe('format');
    expect(errors[1].key).toBe('duplicate');
    expect(errors[2].key).toBe('duplicate');
    expect(errors[3].options).toBe('required');
    expect(fieldDefsHaveErrors(errors)).toBe(true);
  });

  it('allows inactive duplicate labels', () => {
    const errors = fieldDefRowErrors([
      { key: 'a', label: 'Color', type: 'text', active: true },
      { key: 'b', label: 'Color', type: 'text', active: false },
    ]);
    expect(errors[0].label).toBeUndefined();
    expect(errors[1].label).toBeUndefined();
  });

  it('treats Brand form and Brand_form as the same active label', () => {
    const errors = fieldDefRowErrors([
      { key: 'brandForm', label: 'Brand form', type: 'text', active: true },
      { key: 'other', label: 'Brand_form', type: 'text', active: true },
    ]);
    expect(errors[0].label).toBe('duplicate');
    expect(errors[1].label).toBe('duplicate');
  });

  it('flags reserved item column names', () => {
    const errors = fieldDefRowErrors([
      { key: 'sku', label: 'Our code', type: 'text', active: true },
      { key: 'shade', label: 'Name', type: 'text', active: true },
    ]);
    expect(errors[0].key).toBe('reserved');
    expect(errors[1].label).toBe('reserved');
  });

  it('flags JSON lookup names as reserved keys', () => {
    const errors = fieldDefRowErrors([
      { key: 'contains', label: 'Contains', type: 'text', active: true },
    ]);
    expect(errors[0].key).toBe('reserved');
  });

  it('flags a label that collides with another field key', () => {
    const errors = fieldDefRowErrors([
      { key: 'color', label: 'Shade', type: 'text', active: true },
      { key: 'tint', label: 'Color', type: 'text', active: true },
    ]);
    expect(errors[1].label).toBe('duplicate');
  });

  it('flags overlong keys, labels, and options', () => {
    const errors = fieldDefRowErrors([
      { key: 'a'.repeat(65), label: 'Ok', type: 'text', active: true },
      { key: 'okKey', label: 'L'.repeat(81), type: 'text', active: true },
      { key: 'form', label: 'Form', type: 'list', active: true, options: ['x'.repeat(81)] },
    ]);
    expect(errors[0].key).toBe('max');
    expect(errors[1].label).toBe('max');
    expect(errors[2].options).toBe('length');
  });
});

describe('parseCfSearchParams / extraValues', () => {
  it('parses repeated cf keys', () => {
    const params = new URLSearchParams('cf.form=Strip&cf.form=Bottle&q=tea');
    expect(parseCfSearchParams(params)).toEqual({ form: ['Strip', 'Bottle'] });
  });

  it('unions distinct stored values', () => {
    const extra = extraValuesFromProducts([
      { customFields: { form: 'Strip', color: 'Red' } },
      { customFields: { form: 'Jar', color: 'Red' } },
    ]);
    expect(extra.form).toEqual(['Strip', 'Jar']);
    expect(extra.color).toEqual(['Red']);
  });
});

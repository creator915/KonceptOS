export class Seed {
  constructor() {
    this.domain = '';
    this.obj_vocab = [];
    this.attr_vocab = [];
    this.obj_tree = {};
    this.attr_tree = {};
    this.incidence_hints = {};
    this.conventions = [];
    this.reference_k = null;
  }

  lookup_obj(name) {
    if (name in this.obj_tree) return this.obj_tree[name];
    for (const [k, v] of Object.entries(this.obj_tree)) {
      if (k.includes(name) || name.includes(k)) return v;
    }
    return null;
  }

  lookup_attr(name) {
    if (name in this.attr_tree) return this.attr_tree[name];
    for (const [k, v] of Object.entries(this.attr_tree)) {
      if (k.includes(name) || name.includes(k)) return v;
    }
    return null;
  }

  has_content() {
    return !!(Object.keys(this.obj_tree).length || Object.keys(this.attr_tree).length ||
              this.obj_vocab.length || this.attr_vocab.length ||
              this.conventions.length || this.reference_k);
  }

  conventions_text() {
    return this.conventions.map(c => `- ${c}`).join('\n');
  }

  to_dict() {
    return {
      domain: this.domain,
      obj_vocab: this.obj_vocab,
      attr_vocab: this.attr_vocab,
      obj_tree: this.obj_tree,
      attr_tree: this.attr_tree,
      incidence_hints: this.incidence_hints,
      conventions: this.conventions,
      reference_k: this.reference_k
    };
  }

  from_dict(d) {
    this.domain = d.domain || '';
    this.obj_vocab = d.obj_vocab || [];
    this.attr_vocab = d.attr_vocab || [];
    this.obj_tree = d.obj_tree || {};
    this.attr_tree = d.attr_tree || {};
    this.incidence_hints = d.incidence_hints || {};
    this.conventions = d.conventions || [];
    this.reference_k = d.reference_k || null;
  }
}

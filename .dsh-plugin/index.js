module.exports = {
  name: "chelate-shell",
  apply: function(ctx) {
    console.log("[chelate-shell] Activated via CJS.");
    return { status: "active" };
  }
};

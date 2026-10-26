(function () {
    var btn = document.getElementById("menuBtn");
    var sidebar = document.getElementById("sidebar");
    if (btn && sidebar) {
        btn.addEventListener("click", function () {
            sidebar.classList.toggle("open");
        });
    }
})();

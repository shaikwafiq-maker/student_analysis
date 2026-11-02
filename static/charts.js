// Draw the interactive charts. Called after Chart.js has loaded.
window.initCharts = function () {
  var holder = document.getElementById("chart-data");
  if (!holder || !window.Chart) { return; }
  var d = JSON.parse(holder.textContent);
  var dark = document.documentElement.getAttribute("data-theme") === "dark";
  var textColor = dark ? "#aebbd5" : "#4a5866";
  var gridColor = dark ? "rgba(92,108,145,.19)" : "rgba(70,90,120,.12)";
  Chart.defaults.color = textColor;
  Chart.defaults.borderColor = gridColor;
  Chart.defaults.font.family = "Segoe UI, Arial, sans-serif";
  Chart.defaults.font.size = 11;
  var palette = ["#7c8cff", "#48d9b0", "#49c8ee", "#bd8cff", "#ffc96b", "#ff8ca8", "#8f9bb7"];
  var gradeColors = ["#48d9b0", "#7c8cff", "#49c8ee", "#bd8cff", "#ffc96b", "#ff9b78", "#ff6f91"];

  function draw(id, config) {
    var canvas = document.getElementById(id);
    if (canvas) {
      var existing = Chart.getChart(canvas);
      if (existing) { existing.destroy(); }
      new Chart(canvas, config);
    }
  }
  function axisTitle(text) { return { display: true, text: text, color: textColor, padding: { top: 8 } }; }
  var plain = {
    responsive: true, maintainAspectRatio: false,
    plugins: { legend: { display: false }, tooltip: { displayColors: true, backgroundColor: dark ? "#202b43" : "#17212b", titleColor: "#fff", bodyColor: "#e8edff", padding: 11, cornerRadius: 9 } },
    scales: {
      x: { grid: { display: false }, ticks: { color: textColor } },
      y: { beginAtZero: true, grid: { color: gridColor, drawBorder: false }, ticks: { color: textColor, padding: 7 } }
    }
  };

  draw("chartSubjects", {
    type: "bar",
    data: { labels: d.subjects.labels, datasets: [{ label: "Average marks", data: d.subjects.average,
      backgroundColor: palette, borderRadius: 7, borderSkipped: false, maxBarThickness: 36 }] },
    options: Object.assign({}, plain, { scales: Object.assign({}, plain.scales, { y: Object.assign({}, plain.scales.y, { suggestedMax: 100, title: axisTitle("Average marks") }) }) })
  });
  draw("chartPass", {
    type: "bar",
    data: { labels: d.subjects.labels, datasets: [{ label: "Passed (%)", data: d.subjects.pass,
      backgroundColor: "rgba(72,217,176,.82)", hoverBackgroundColor: "#48d9b0", borderRadius: 7, borderSkipped: false, maxBarThickness: 36 }] },
    options: Object.assign({}, plain, { scales: Object.assign({}, plain.scales, { y: Object.assign({}, plain.scales.y, { max: 100, title: axisTitle("Students passed (%)") }) }) })
  });
  draw("chartGrades", {
    type: "doughnut",
    data: { labels: d.grades.labels, datasets: [{ data: d.grades.counts, backgroundColor: gradeColors,
      borderColor: dark ? "#141d31" : "#ffffff", borderWidth: 4, hoverOffset: 7 }] },
    options: { responsive: true, maintainAspectRatio: false, cutout: "69%", plugins: {
      legend: { position: "bottom", labels: { usePointStyle: true, pointStyle: "circle", padding: 14, color: textColor, boxWidth: 7, boxHeight: 7 } },
      tooltip: { backgroundColor: dark ? "#202b43" : "#17212b", titleColor: "#fff", bodyColor: "#e8edff", padding: 11, cornerRadius: 9 }
    } }
  });

  var box = document.getElementById("studentBox");
  if (box) { box.style.height = Math.max(280, d.students.labels.length * 28 + 70) + "px"; }
  draw("chartStudents", {
    type: "bar",
    data: { labels: d.students.labels, datasets: [{ label: "Percentage", data: d.students.percentage,
      backgroundColor: d.students.failed.map(function (f) { return f ? "#ff7896" : "#7c8cff"; }), borderRadius: 5, borderSkipped: false }] },
    options: Object.assign({}, plain, { indexAxis: "y", scales: { x: { beginAtZero: true, max: 100, grid: { color: gridColor }, title: axisTitle("Percentage (red = failed a subject)") }, y: { grid: { display: false } } } })
  });
};

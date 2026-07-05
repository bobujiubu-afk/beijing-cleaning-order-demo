(function () {
  function setTip(message) {
    var tip = document.querySelector("#locationTip");
    if (tip) tip.textContent = message;
  }

  function fillFallback(latitude, longitude) {
    var address = document.querySelector("#addressInput");
    var mapLink = "https://uri.amap.com/marker?position=" + longitude + "," + latitude + "&name=客户定位";
    if (address) {
      address.value = "客户定位：" + latitude.toFixed(6) + "," + longitude.toFixed(6) + " " + mapLink;
      address.dispatchEvent(new Event("input", { bubbles: true }));
    }
    setTip("已填入定位坐标和地图链接，老板可复制打开查看。");
  }

  async function reverseGeocode(latitude, longitude) {
    var url = "https://nominatim.openstreetmap.org/reverse?format=jsonv2&accept-language=zh-CN&lat=" + latitude + "&lon=" + longitude;
    var response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error("reverse geocode failed");
    var data = await response.json();
    return data.display_name || "";
  }

  document.addEventListener("DOMContentLoaded", function () {
    var button = document.querySelector("#locateButton");
    if (!button) return;
    button.addEventListener("click", function () {
      if (!navigator.geolocation) {
        setTip("当前浏览器不支持定位，请手动填写服务地址。");
        return;
      }

      button.disabled = true;
      button.textContent = "定位中...";
      setTip("请在浏览器弹窗中允许定位。");

      navigator.geolocation.getCurrentPosition(
        async function (position) {
          var latitude = position.coords.latitude;
          var longitude = position.coords.longitude;
          try {
            var addressText = await reverseGeocode(latitude, longitude);
            var address = document.querySelector("#addressInput");
            if (address && addressText) {
              address.value = addressText;
              setTip("已自动填入定位地址，请再补充楼号、单元、门牌等详细信息。");
            } else {
              fillFallback(latitude, longitude);
            }
          } catch (error) {
            fillFallback(latitude, longitude);
          } finally {
            button.disabled = false;
            button.textContent = "自动定位";
          }
        },
        function () {
          button.disabled = false;
          button.textContent = "自动定位";
          setTip("定位未授权或获取失败，请手动填写服务地址。");
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
      );
    });
  });
})();

using UnityEngine;

namespace OriginReal.Integration.Runtime
{
    /// <summary>단일 Rigidbody 루트: Player 태그 오브젝트를 XZ 평면에서 추적.</summary>
    [RequireComponent(typeof(Rigidbody))]
    public sealed class ChasePlayer : MonoBehaviour
    {
        [SerializeField] string playerTag = "Player";
        [SerializeField] float force = 30f;

        Rigidbody _rb;
        Transform _target;

        void Awake()
        {
            _rb = GetComponent<Rigidbody>();
            var go = GameObject.FindGameObjectWithTag(playerTag);
            if (go != null) _target = go.transform;
        }

        void FixedUpdate()
        {
            if (_target == null) return;

            Vector3 d = _target.position - transform.position;
            d.y = 0;
            if (d.sqrMagnitude < 0.01f) return;
            d.Normalize();

            _rb.AddForce(d * force, ForceMode.Force);
            transform.rotation = Quaternion.LookRotation(d);
        }
    }
}
